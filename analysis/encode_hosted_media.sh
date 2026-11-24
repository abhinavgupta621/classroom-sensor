#!/bin/sh
# Small copies of each class for the hosted (read-only) portal: mono 32 kbps audio, and the room
# camera at 384 px wide, 10 fps, cut into 15-minute files with the class audio.
#   sh analysis/encode_hosted_media.sh [session dirs...]   ->  data/portal/hosted/{audio,video}/
set -e
cd "$(dirname "$0")/.."
OUT=data/portal/hosted
[ $# -gt 0 ] || set -- data/media/*-core-section-a
for sd in "$@"; do
  d=$(basename "$sd" | cut -c1-10)
  [ -f "$OUT/audio/$d.m4a" ] || ffmpeg -nostdin -loglevel error -y -i "$sd/audio.m4a" -ac 1 -c:a aac -b:a 32k -movflags +faststart "$OUT/audio/$d.m4a"
  mkdir -p "$OUT/video/$d"
  [ -f "$OUT/video/$d/0.mp4" ] || ffmpeg -nostdin -loglevel error -y -i "$sd/camera.mp4" -i "$sd/audio.m4a" -map 0:v:0 -map 1:a:0 \
    -vf "scale=384:-2,fps=10" -c:v libx264 -preset veryfast -crf 32 -g 50 -force_key_frames "expr:gte(t,n_forced*900)" -c:a aac -ac 1 -b:a 32k \
    -f segment -segment_time 900 -reset_timestamps 1 -segment_format_options movflags=+faststart "$OUT/video/$d/%d.mp4"
  echo "done $d"
done
