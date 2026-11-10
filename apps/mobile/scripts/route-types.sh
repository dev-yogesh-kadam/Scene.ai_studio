#!/usr/bin/env bash
# Rewrite .expo/types/router.d.ts (the typed routes `tsc` checks links against) after adding or moving a screen.
# Expo writes it only while its dev server runs, so this starts one on a spare port until the file is new, then stops it.
set -u
cd "$(dirname "$0")/.."
before=$(stat -c %Y .expo/types/router.d.ts 2>/dev/null || echo 0)
(CI=1 timeout 60 npx expo start --port 8099 --go > /dev/null 2>&1 &)
for _ in $(seq 1 50); do
  sleep 1
  now=$(stat -c %Y .expo/types/router.d.ts 2>/dev/null || echo 0)
  [ "$now" != "$before" ] && break
done
sleep 1
for pid in $(netstat -ano | grep LISTENING | grep ":8099 " | awk '{print $5}' | sort -u); do taskkill //PID "$pid" //T //F > /dev/null 2>&1; done
echo "route types written"
