#!/bin/bash

echo " ---- Installing nvm and Node.js ---- "
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | PROFILE=~/.zshrc bash

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

nvm install 22
nvm use 22
echo "Node version: $(node -v)"

echo " ---- Checking gcloud installation ---- "
gcloud --version
gcloud config list project

echo " ---- Setting up Python environment ---- "
uv python install 3.13
uv python pin 3.13

echo " ---- Updating Claude CLI ---- "
claude install
claude update

echo " ---- Setting up GitNexus ---- "
npm install -g gitnexus
gitnexus setup

echo " ---> ✅ Post-create command completed ✅ <--- "
