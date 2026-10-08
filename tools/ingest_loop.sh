#!/usr/bin/env bash
# The ingest daemon: one Actions job that runs the pipeline every 5 minutes
# for up to ~5.5 hours (just under the 6-hour job cap), because GitHub's
# cron scheduler fires a */5 schedule only every few hours in practice
# (measured 25 Sep - 8 Oct 2026: median 3.5 h between runs, worst 12.2 h,
# every run green). The schedule's real job is now just to QUEUE the next
# daemon behind this one (concurrency group, cancel-in-progress false).
#
# Commits are kept meaningful: push when the ITEMS changed, or as a
# heartbeat when 45 minutes have passed since the last commit - so the
# drawer's one-hour staleness dot means "pipeline dead", never "quiet news",
# and the repo does not swell with timestamp-only commits.
set -u

LOOP_SECONDS="${LOOP_SECONDS:-300}"
RUN_FOR_SECONDS="${RUN_FOR_SECONDS:-19800}"   # ~5.5 h
HEARTBEAT_SECONDS="${HEARTBEAT_SECONDS:-2700}" # 45 min

git config user.name  "pes-newsfeed"
git config user.email "actions@github.com"

push_with_retry() {
  # A push can lose a race with the calendar/annotations jobs or hit a
  # transient GitHub 500. Rebase on whatever landed and retry; -X theirs
  # keeps THIS run's regenerated news.json on conflict (rebase flips
  # ours/theirs: "theirs" is the commit being replayed, i.e. ours).
  for attempt in 1 2 3; do
    if git pull --rebase --autostash -X theirs origin "${GITHUB_REF_NAME:-main}" && git push; then
      return 0
    fi
    git rebase --abort 2>/dev/null || true
    echo "push attempt ${attempt} failed - retrying"
    sleep $((attempt * 10))
  done
  echo "push failed after 3 attempts" >&2
  return 1
}

end=$((SECONDS + RUN_FOR_SECONDS))
tick=0
while [ "$SECONDS" -lt "$end" ]; do
  tick=$((tick + 1))
  tick_started=$SECONDS
  echo "=== tick ${tick} at $(date -u +'%H:%M:%S') UTC ==="

  touch .env
  if ! python src/ingest.py; then
    # One bad sweep (a source timing out hard, a transient DNS wobble) must
    # not kill the daemon; the next tick retries. Leave the tree clean.
    echo "ingest failed on tick ${tick} - will retry next tick"
    git checkout -- data/news.json 2>/dev/null || true
  else
    new_items=$(jq -S '.items' data/news.json)
    old_items=$(git show HEAD:data/news.json 2>/dev/null | jq -S '.items' 2>/dev/null || echo "")
    last_ts=$(git log -1 --format=%ct -- data/news.json 2>/dev/null || echo 0)
    age=$(( $(date +%s) - last_ts ))
    if [ "$new_items" != "$old_items" ]; then
      git add data/news.json
      git commit -m "feed update $(date -u +'%Y-%m-%dT%H:%MZ')"
      push_with_retry || exit 1
    elif [ "$age" -gt "$HEARTBEAT_SECONDS" ]; then
      git add data/news.json
      git commit -m "feed heartbeat $(date -u +'%Y-%m-%dT%H:%MZ') (no new items; generated_at refreshed)"
      push_with_retry || exit 1
    else
      # Nothing new and the heartbeat is fresh: drop the timestamp-only
      # rewrite so the tree stays clean.
      git checkout -- data/news.json
      echo "no item changes (heartbeat ${age}s old) - nothing to push"
    fi
  fi

  elapsed=$((SECONDS - tick_started))
  remaining=$((LOOP_SECONDS - elapsed))
  if [ "$remaining" -gt 0 ] && [ "$SECONDS" -lt "$end" ]; then
    sleep "$remaining"
  fi
done
echo "daemon window complete after ${tick} ticks - the queued run takes over"
