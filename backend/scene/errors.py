"""What a failed job's error means, in plain words: for the admin console (the job's details) and for the person whose
job it was (the canvas shows a failed job with its reason)."""

# What a failed job's error means, in words for the admin: (part of the message, explanation). The first match wins.
PLAIN_ERRORS = [
    ("app was restarted", "The studio app was restarted while this job ran, so it could not finish."),
    ("studio restarted while this ran on this pc", "The studio app was restarted while this ran on this PC, so it could not finish."),
    ("no provider has a key for", "No provider key in use has this model now. The studio's admin can add one in Servers & APIs → Providers."),
    ("comfyui workflow, which the studio no longer uses", "It was made with a ComfyUI workflow, which the studio no longer uses: make it again with one of the models."),
    ("is not set up on this pc", "A tool on this PC that the job needs is not set up. The studio's admin can set it up (docs/servers.md)."),
    ("finished but sent no", "The provider finished but sent no picture, video or sound."),
    ("hyperframes", "The motion graphic could not be drawn on this machine."),
    ("ffmpeg", "Joining or cutting the video failed on this machine."),
    ("switched off in the console", "The model that makes this kind of work is switched off now. The studio's admin can switch it on."),
]


def explain(error):
    if not error:
        return ""
    if error.startswith("The provider: "):   # written for people (jobs._finish)
        return error
    low = error.lower()
    for words, meaning in PLAIN_ERRORS:
        if words in low:
            return meaning
    return ""


def for_user(error):
    """The reason a job failed, as the person whose job it was reads it: the plain meaning when it is known, or a
    general one."""
    return explain(error) or ("Something went wrong while it was being made." if error else "")
