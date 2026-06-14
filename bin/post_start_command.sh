#!/bin/bash

# prepare pyhton env
echo " ---- Setting up Python environment ---- "
if [ -f ".venv/bin/activate" ]; then
    echo "Activating virtual environment..."
else
    echo "Virtual environment not found. Creating one..."
    uv venv .venv
    uv sync
fi
source .venv/bin/activate

# prepare gitnexus
echo " ---- Setting up GitNexus ---- "
gitnexus analyze
gitnexus index

echo " ---> ✅ Post-start command completed ✅ <--- "
