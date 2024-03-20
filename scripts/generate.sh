#!/bin/bash

# warning silencing for sed
WARN_EDGES=", correcting"
FREESTYLE_RENDER="Fra:"
CYCLES_RENDER="Scene, ViewLayer"
COMPOSITING="Compositing | Tile"
ANIMATION_SEQUENCER="Append"
TIME_INFO=" Time:"
NEW_LINE="^$"

if unbuffer g2b_blender --python-exit-code 1 -b --python-expr "import gerber2blend ; gerber2blend.main()" -- $@; then
  exit 0
else
  echo 1 >> tempblend
fi | grep -v --line-buffered "$WARN_EDGES\|$FREESTYLE_RENDER\|$CYCLES_RENDER\|$COMPOSITING\|$ANIMATION_SEQUENCER\|$TIME_INFO\|$NEW_LINE" | tee ./log;

if [ -f tempblend ]; then
  rm tempblend
  exit 1
fi
