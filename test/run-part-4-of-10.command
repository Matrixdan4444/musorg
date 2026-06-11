#!/bin/zsh
set -euo pipefail
unsetopt BG_NICE

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
START_TIME=$SECONDS

cd "$REPO_ROOT"
echo "Running match stress part 4/10..."
set +e
("$REPO_ROOT/venv/bin/python" "$REPO_ROOT/test/run_match_part.py" 4 "$@") &
runner_pid=$!

spinner_frames=("◐" "◓" "◑" "◒")
spinner_index=1
while kill -0 "$runner_pid" 2>/dev/null; do
  printf "\r%s running part 4/10..." "${spinner_frames[$spinner_index]}"
  spinner_index=$((spinner_index % ${#spinner_frames[@]} + 1))
  sleep 0.12
done

wait "$runner_pid"
exit_code=$?
set -e
printf "\r"
if [[ $exit_code -eq 0 ]]; then
  echo "Part 4/10 finished."
else
  echo "Part 4/10 stopped with exit code $exit_code."
fi
ELAPSED_SECONDS=$((SECONDS - START_TIME))
printf 'Elapsed time: %02d:%02d:%02d\n' $((ELAPSED_SECONDS / 3600)) $(((ELAPSED_SECONDS % 3600) / 60)) $((ELAPSED_SECONDS % 60))

echo
if [[ -z "${MUSORG_NO_PAUSE:-}" ]]; then
  read -r "?Press Enter to close..."
fi

exit $exit_code
