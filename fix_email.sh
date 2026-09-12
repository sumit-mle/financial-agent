#!/bin/bash
git filter-branch -f --env-filter '
if [ "$GIT_COMMITTER_EMAIL" = "your.email@example.com" ]; then
  export GIT_COMMITTER_EMAIL="sumit.kgpiit@gmail.com"
  export GIT_COMMITTER_NAME="Sumit Kumar"
fi
if [ "$GIT_AUTHOR_EMAIL" = "your.email@example.com" ]; then
  export GIT_AUTHOR_EMAIL="sumit.kgpiit@gmail.com"
  export GIT_AUTHOR_NAME="Sumit Kumar"
fi
' -- --all
