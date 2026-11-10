"""Copy the studio's media between this machine's folders and Azure Blob Storage, either way, checking each file.

    python scripts/move_media.py to-azure  [--dry-run] [--connection-string ... | --account-url ...] [--container scene]
    python scripts/move_media.py to-local  [--dry-run] [...]

Every kind (outputs, posters, kit, showcase: storage.py) is copied file by file: a file already on the other side with
the same size and MD5 is left as it is, so a run that was cut short goes on where it stopped when run again. Each copy
is checked after it is made (its size and MD5 on the other side) and a file that comes out different is reported and
counted as failed. Nothing is deleted on either side. --dry-run says what would be copied and copies nothing.

The folders are the ones config.json names (output_dir; storage_dir's assets and showcase), the container
azure_storage_container, signed in with azure_storage_connection_string or azure_storage_account_url (the account's
URL and DefaultAzureCredential: az login, or a managed identity), unless given here.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from scene import storage  # noqa: E402
from scene.config import load_settings  # noqa: E402


def roots(settings):
    data = settings.path("storage_dir")
    outputs = settings.path("output_dir") if settings.output_dir else data / "outputs"
    return {"outputs": outputs, "posters": outputs, "kit": data / "assets", "showcase": data / "showcase"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("direction", choices=("to-azure", "to-local"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--connection-string")
    parser.add_argument("--account-url")
    parser.add_argument("--container")
    args = parser.parse_args()

    settings = load_settings()
    folders = roots(settings)
    local = storage.LocalStorage(folders)
    azure = storage.AzureBlobStorage(args.container or settings.azure_storage_container, folders,
                                     connection_string=args.connection_string if args.connection_string is not None
                                     else (settings.azure_storage_connection_string if not args.account_url else ""),
                                     account_url=args.account_url or settings.azure_storage_account_url)
    source, target = (local, azure) if args.direction == "to-azure" else (azure, local)
    copied = same = failed = 0
    size = 0
    for kind in storage.KINDS:
        there = {key: (n, md5) for key, n, md5 in target.list(kind)}
        for key, n, md5 in source.list(kind):
            if md5 is None:   # this machine's files: their MD5 is worked out here
                md5 = storage.md5_of(local.local(kind, key))
            have = there.get(key)
            if have and have[0] == n:   # the same size there: the same file if its MD5 is the same too
                have_md5 = have[1] if have[1] is not None else storage.md5_of(target.local(kind, key))
                if have_md5 == md5:
                    same += 1
                    continue
            if args.dry_run:
                print("would copy  {}/{}  ({:,} bytes)".format(kind, key, n))
                copied += 1
                size += n
                continue
            if target is azure:
                azure.save(kind, key, local.local(kind, key))
                after = azure.blob(kind, key).get_blob_properties()
                got_size = after.size
                got_md5 = bytes(after.content_settings.content_md5).hex() if after.content_settings.content_md5 else None
            else:
                path = local.local(kind, key)
                path.parent.mkdir(parents=True, exist_ok=True)
                partial = path.with_name(path.name + ".partial")
                with open(partial, "wb") as f:
                    azure.blob(kind, key).download_blob().readinto(f)
                partial.replace(path)
                got_size, got_md5 = path.stat().st_size, storage.md5_of(path)
            if got_size != n or got_md5 != md5:
                print("DIFFERENT   {}/{}: {} bytes, md5 {} there; {} bytes, md5 {} here".format(kind, key, got_size, got_md5, n, md5))
                failed += 1
                continue
            copied += 1
            size += n
            print("copied      {}/{}".format(kind, key))
    print("{} {} ({:,} bytes), {} already the same, {} failed".format(
        "Would copy" if args.dry_run else "Copied", copied, size, same, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
