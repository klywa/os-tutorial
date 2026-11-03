#!/usr/bin/env bash
# Install root-owned at /usr/local/sbin/deploy-os-tutorial-from-github.
# The dedicated authorized_keys entry forces this command and disables forwarding.
set -euo pipefail

if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
  echo 'Only deploy <40-character commit SHA> is accepted.' >&2
  exit 64
fi
expected_commit=${BASH_REMATCH[1]}

/usr/local/bin/update-sites --os-tutorial
systemctl is-active --quiet os-tutorial.service
runuser -u os-tutorial -- git -C /opt/os-tutorial/current \
  merge-base --is-ancestor "$expected_commit" HEAD
deployed_commit=$(runuser -u os-tutorial -- git -C /opt/os-tutorial/current rev-parse HEAD)
printf 'Deployed and verified: %s\n' "$deployed_commit"
