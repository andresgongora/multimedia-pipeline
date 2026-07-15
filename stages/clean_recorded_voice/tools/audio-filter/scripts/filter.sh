#!/usr/bin/env bash
set -euo pipefail

# Canonical production filter. Runs inside the audio-filter Docker image.
# Container lifecycle (--rm) handles all temp file cleanup.
#
# Stage pipeline:
#  1. DeepFilterNet   — broadband noise suppression (--dfn-atten-db, default 20)
#  2. ffmpeg chain    — highpass, boom cuts, harshness notches, body boost, exciter
#  3. loudnorm 2-pass — pass 1 measures true loudness, pass 2 applies linear gain (lossless)

##==================================================================================================
##  Requirements
##==================================================================================================

## Validates that a required command exists in PATH.
require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Aborting: '$command_name' not found in PATH"
    exit 1
  }
}

## Validates that an input file exists before processing.
require_file() {
  local file_path="$1"
  [[ -f "$file_path" ]] || {
    echo "Input file not found: $file_path"
    exit 1
  }
}


##==================================================================================================
##  DeepFilterNet
##==================================================================================================

## Applies DeepFilterNet noise suppression to an audio input file and returns enhanced WAV path.
apply_deepfilternet() {
  local input_file="$1"
  local deepfilter_bin="${2:-}"
  local tmp_dir="${3:-}"
  local atten_lim_db="${4:-100}"

  [[ -n "$deepfilter_bin" ]] || {
    echo "DeepFilterNet binary path not provided" >&2
    return 1
  }

  [[ -n "$tmp_dir" ]] || {
    echo "Temporary directory not provided" >&2
    return 1
  }

  require_file "$input_file"

  # Convert to 48 kHz float WAV, strip sub-bass thuds, and declip in one pass.
  # This merges convert_to_temp_wav + deepfilter_prepare_wav to avoid an intermediate encode.
  local limited_wav
  limited_wav="$(mktemp -p "$tmp_dir" --suffix=.wav)"
  ffmpeg -hide_banner -y \
    -i "$input_file" \
    -af "aresample=48000,alimiter=limit=0.891:level=false,highpass=f=70:p=2,alimiter=limit=0.891:level=false" \
    -c:a pcm_f32le \
    "$limited_wav" 1>&2

  local df_output_dir
  df_output_dir="$(mktemp -d -p "$tmp_dir")"

  echo "[DEEP FILTER START]" >&2
  if ! "$deepfilter_bin" --atten-lim-db "$atten_lim_db" -o "$df_output_dir" "$limited_wav" 1>&2; then
    echo "DeepFilterNet processing failed" >&2
    echo "[DEEP FILTER END - FAILED]" >&2
    return 1
  fi
  echo "[DEEP FILTER END - SUCCESS]" >&2

  local enhanced_wav
  enhanced_wav="$(find "$df_output_dir" -name "*.wav" -type f | head -1)"
  [[ -n "$enhanced_wav" ]] || {
    echo "No enhanced WAV found in DeepFilterNet output directory: $df_output_dir" >&2
    return 1
  }

  echo "$enhanced_wav"
}



##==================================================================================================
##  Filter workflow
##==================================================================================================

## Measures the integrated loudness of a WAV and returns the gain in dB needed to reach
## a consistent working level (-23 LUFS) before the filter chain.
##
## Why: gate, compressor, and deesser thresholds in build_filter_chain() are absolute
## amplitude values. Without pre-normalization a quiet recording (~-30 LUFS) barely
## activates those stages, producing very different results than a loud one (~-14 LUFS).
## Pre-normalizing gives every recording the same starting point regardless of capture gain.
##
## -23 LUFS target provides ~9 dB headroom below the -14 LUFS delivery target,
## leaving room for compressor makeup gain and exciter without risking clipping.
##
## The caller prepends "volume=${gain_db}dB," to the filter chain so no intermediate WAV
## is written — the gain is applied inline during the existing loudnorm passes.
##
## Clicks or loud transients do NOT prevent voice boost: integrated loudness (EBU R128)
## averages over the whole file, so a brief click has negligible influence on the measured
## level. Any transient that clips slightly will be repaired by adeclick in the chain.
measure_prenorm_gain() {
  local input_wav="$1"
  local target_lufs="${2:--23}"

  local ffmpeg_stderr
  ffmpeg_stderr="$(
    ffmpeg -hide_banner -y \
      -i "$input_wav" \
      -af "loudnorm=I=${target_lufs}:TP=-1:LRA=20:print_format=json" \
      -f null - 2>&1
  )"

  local json_block
  json_block="$(echo "$ffmpeg_stderr" | grep -A 20 '\[Parsed_loudnorm' | grep -A 20 '{' | sed -n '/{/,/}/p' | head -20)"

  local input_i
  input_i="$(echo "$json_block" | sed -n 's/.*"input_i"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

  if [[ -z "$input_i" ]]; then
    echo "prenorm: loudness measurement failed — using 0 dB gain" >&2
    echo "0.00"
    return 0
  fi

  local gain_db
  gain_db="$(awk "BEGIN {printf \"%.2f\", ${target_lufs} - (${input_i})}")"
  echo "prenorm: input=${input_i} LUFS, gain=${gain_db} dB → ${target_lufs} LUFS working level" >&2
  echo "$gain_db"
}
prenormalize() {
  local input_wav="$1"
  local tmp_dir="$2"
  local target_lufs="${3:--23}"

  # Measure integrated loudness (null sink — no encode)
  local ffmpeg_stderr
  ffmpeg_stderr="$(
    ffmpeg -hide_banner -y \
      -i "$input_wav" \
      -af "loudnorm=I=${target_lufs}:TP=-1:LRA=20:print_format=json" \
      -f null - 2>&1
  )"

  local json_block
  json_block="$(echo "$ffmpeg_stderr" | grep -A 20 '\[Parsed_loudnorm' | grep -A 20 '{' | sed -n '/{/,/}/p' | head -20)"

  local input_i
  input_i="$(echo "$json_block" | sed -n 's/.*"input_i"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

  if [[ -z "$input_i" ]]; then
    echo "prenormalize: loudness measurement failed — skipping gain correction" >&2
    echo "$input_wav"
    return 0
  fi

  # Compute gain delta and apply as linear volume shift (lossless on float PCM)
  local gain_db
  gain_db="$(awk "BEGIN {printf \"%.2f\", ${target_lufs} - (${input_i})}")"
  echo "prenormalize: input=${input_i} LUFS, gain=${gain_db} dB → ${target_lufs} LUFS working level" >&2

  local normalized_wav
  normalized_wav="$(mktemp -p "$tmp_dir" --suffix=.wav)"

  ffmpeg -hide_banner -y \
    -i "$input_wav" \
    -af "volume=${gain_db}dB" \
    -c:a pcm_f32le \
    "$normalized_wav" 1>&2

  echo "$normalized_wav"
}

## Builds the voice filter chain for spoken-word clarity and pleasant listening.
##
## Pre-condition: input has been pre-normalized to ~-23 LUFS (see prenormalize()).
## This ensures all level-sensitive stages operate on a consistent signal level.
##
## Stage-by-stage rationale:
##
##  1. highpass=f=80:p=1
##     Remove sub-bass rumble, handling noise, and DC offset. 1st-order (6 dB/oct) is
##     gentle — avoids ringing artefacts on voice fundamentals near 80-120 Hz.
##
##  2. adeclick=w=35:o=60:a=0.8
##     Repair isolated clicks, mic taps, mouth pops, and electrical pops before
##     spectral processing so clicks don't smear across frequency bands.
##
##  3. afftdn=nr=4:nf=-30:tn=1
##     Residual broadband noise reduction (spectral subtraction). Light settings
##     (nr=4) because DeepFilterNet already did heavy lifting; this catches remaining
##     low-level hiss and room noise without blurring voice transients.
##
##  4. agate=mode=downward:threshold=0.018:ratio=1.6:attack=20:release=240:range=0.12
##     Gently attenuate very quiet passages — breath noise and room tone between
##     sentences. Downward mode with low ratio (1.6) and limited range (0.12 = 12%)
##     is audibly transparent. Pre-normalization ensures voice reliably exceeds threshold.
##
##  5. equalizer=f=160:t=q:w=4:g=-2.5
##     Cut low-mid boxiness/muddiness typical of lavalier mics in small rooms.
##
##  6. equalizer=f=3000:t=q:w=6:g=-3.0
##     Reduce upper-mid harshness (3 kHz presence peak). Male voice can sound
##     nasal or aggressive here, especially with budget lavalier capsules.
##
##  7. equalizer=f=4500:t=q:w=5:g=-2.5
##     Reduce "dental" edge — hard T and D consonants and capsule distortion peak here.
##
##  8. equalizer=f=7500:t=q:w=3:g=-1.5
##     Soften air-band bite that clip-on lavs tend to exaggerate.
##
##  9. highshelf=f=9000:g=-2.0
##     Roll off top-end air and hiss gently. Prevents shrill or thin sound after
##     the mid-range cuts above.
##
## 10. lowshelf=f=200:g=1.8
##     Restore warmth and body after the mid cuts. Counteracts thinning from EQ
##     and gives the voice natural weight on playback.
##
## 11. deesser=i=0.35:m=0.75:f=0.65
##     Tame sibilance (S, T sounds). Applied before compression so sibilants
##     cannot pump the compressor's gain reduction.
##
## 12. acompressor=threshold=0.18:ratio=2.5:attack=25:release=160:knee=3:makeup=1.5
##     Smooth level variation from head movement or inconsistent mic distance.
##     Moderate ratio (2.5:1) with soft knee — transparent control, not heavy limiting.
##     makeup=1.5 restores loudness lost to gain reduction.
##
## 13. aexciter=level_in=1:level_out=1:amount=1.5:drive=6:blend=-1:freq=6000
##     Add subtle high-frequency harmonic presence (clarity and air). Applied after
##     compression so its contribution is consistent regardless of input dynamics.
##
## 14. alimiter=limit=0.891:release=70
##     True-peak safety ceiling (~-1 dBTP) before loudnorm. Prevents any transient
##     from clipping during the loudnorm measurement pass.
build_filter_chain() {
  local filter_chain

  filter_chain="$(cat <<EOF
highpass=f=80:p=1,
adeclick=w=35:o=60:a=0.8,
afftdn=nr=4:nf=-30:tn=1,
agate=mode=downward:threshold=0.018:ratio=1.6:attack=20:release=240:range=0.12,
equalizer=f=160:t=q:w=4:g=-2.5,
equalizer=f=3000:t=q:w=6:g=-3.0,
equalizer=f=4500:t=q:w=5:g=-2.5,
equalizer=f=7500:t=q:w=3:g=-1.5,
highshelf=f=9000:g=-2.0,
lowshelf=f=200:g=1.8,
deesser=i=0.35:m=0.75:f=0.65,
acompressor=threshold=0.18:ratio=2.5:attack=25:release=160:knee=3:makeup=1.5,
aexciter=level_in=1:level_out=1:amount=1.5:drive=6:blend=-1:freq=6000,
alimiter=limit=0.891:release=70
EOF
)"

  echo "${filter_chain//$'\n'/}"
}

##==================================================================================================
##  Processing
##==================================================================================================

## Resolves ffmpeg codec flags from the output file extension.
codec_flags_for() {
  local output_file="$1"
  local ext="${output_file##*.}"
  case "${ext,,}" in
    wav)            echo "-c:a pcm_s24le" ;;
    m4a|aac|mp4)    echo "-c:a aac -b:a 320k" ;;
    mp3)            echo "-c:a libmp3lame -b:a 320k" ;;
    flac)           echo "-c:a flac" ;;
    ogg)            echo "-c:a libvorbis -q:a 9" ;;
    *)
      echo "Unsupported output format: .${ext} — falling back to AAC" >&2
      echo "-c:a aac -b:a 256k"
      ;;
  esac
}

## Pass 1: runs the filter chain + loudnorm(print_format=json) and parses the measured values.
## Prints four space-separated values: input_i input_tp input_lra input_thresh
measure_loudness() {
  local input_file="$1"
  local process_chain="$2"
  local target_lra="$3"

  # Pass 1: decode to null sink, capture loudnorm JSON from stderr
  local ffmpeg_stderr
  ffmpeg_stderr="$(
    ffmpeg -hide_banner -y \
      -i "$input_file" \
      -af "${process_chain},loudnorm=I=-14:TP=-1:LRA=${target_lra}:print_format=json" \
      -f null - 2>&1
  )"

  # Extract the JSON block that loudnorm prints to stderr
  local json_block
  json_block="$(echo "$ffmpeg_stderr" | grep -A 20 '\[Parsed_loudnorm' | grep -A 20 '{' | sed -n '/{/,/}/p' | head -20)"

  # Parse fields with sed
  local input_i input_tp input_lra input_thresh
  input_i="$(echo    "$json_block" | sed -n 's/.*"input_i"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  input_tp="$(echo   "$json_block" | sed -n 's/.*"input_tp"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  input_lra="$(echo  "$json_block" | sed -n 's/.*"input_lra"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  input_thresh="$(echo "$json_block" | sed -n 's/.*"input_thresh"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

  if [[ -z "$input_i" || -z "$input_tp" || -z "$input_lra" || -z "$input_thresh" ]]; then
    echo "loudnorm pass 1: failed to parse measurement JSON" >&2
    echo "stderr was:" >&2
    echo "$ffmpeg_stderr" >&2
    return 1
  fi

  echo "$input_i $input_tp $input_lra $input_thresh"
}

## Pass 2: encodes with loudnorm using measured values from pass 1.
## linear=false: allows loudnorm to apply gentle dynamic DRC in addition to gain, which
## guarantees hitting the -14 LUFS target even when the TP ceiling would otherwise prevent
## a simple linear gain from fully correcting the level. For voice content this is correct
## behaviour — it is equivalent to what broadcast normalisation tools do.
apply_loudnorm_2pass() {
  local input_file="$1"
  local output_file="$2"
  local process_chain="$3"
  local target_lra="$4"
  local input_i="$5"
  local input_tp="$6"
  local input_lra="$7"
  local input_thresh="$8"

  local codec_flags
  codec_flags="$(codec_flags_for "$output_file")"

  local loudnorm_pass2
  loudnorm_pass2="loudnorm=I=-14:TP=-1:LRA=${target_lra}"
  loudnorm_pass2+=":measured_I=${input_i}:measured_TP=${input_tp}"
  loudnorm_pass2+=":measured_LRA=${input_lra}:measured_thresh=${input_thresh}"
  loudnorm_pass2+=":linear=false:print_format=none"

  # shellcheck disable=SC2086  # word splitting of codec_flags is intentional
  ffmpeg -hide_banner -y \
    -i "$input_file" \
    -af "${process_chain},${loudnorm_pass2}" \
    $codec_flags -ar 48000 \
    "$output_file"
}

##==================================================================================================
##  Main
##==================================================================================================

## Orchestrates DeepFilterNet, filter chain, and two-pass loudness normalization.
main() {
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <input_file> <output_file> [--dfn-atten-db=<0-100>]"
    exit 1
  fi

  local input_file="$1"
  local output_file="$2"
  local dfn_atten_db=20

  # Parse optional flags from remaining args
  local arg
  for arg in "${@:3}"; do
    case "$arg" in
      --dfn-atten-db=*) dfn_atten_db="${arg#*=}" ;;
      *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
  done

  require_command ffmpeg
  require_file "$input_file"

  local tmp_dir="/tmp/audio_processing"
  mkdir -p "$tmp_dir"

  # Stage 1: DeepFilterNet noise suppression.
  # WAV conversion and declipping are handled internally by apply_deepfilternet.
  local deepfilter_bin="/app/tools/deep-filter"
  require_file "$deepfilter_bin"
  echo "Running DeepFilterNet (atten-lim-db=${dfn_atten_db})..." >&2
  local audio_source
  audio_source="$(apply_deepfilternet "$input_file" "$deepfilter_bin" "$tmp_dir" "$dfn_atten_db")"

  # Stage 2: measure the gain needed to reach a consistent -23 LUFS working level.
  # The gain is prepended to the filter chain rather than applied as a separate encode step,
  # so no intermediate WAV is written.
  echo "Measuring pre-normalization gain..." >&2
  local prenorm_gain_db
  prenorm_gain_db="$(measure_prenorm_gain "$audio_source")"

  # Stage 3: voice filter chain + 2-pass loudness normalisation (LRA target: 8 LU)
  # volume= prepended so all level-sensitive filters see a consistent input level.
  local process_chain
  local target_lra=8
  process_chain="volume=${prenorm_gain_db}dB,$(build_filter_chain)"

  echo "Running loudnorm pass 1 (measuring)..." >&2
  local loudnorm_measurements
  loudnorm_measurements="$(measure_loudness "$audio_source" "$process_chain" "$target_lra")"

  local m_i m_tp m_lra m_thresh
  read -r m_i m_tp m_lra m_thresh <<< "$loudnorm_measurements"
  echo "  measured: I=${m_i} TP=${m_tp} LRA=${m_lra} thresh=${m_thresh}" >&2

  echo "Running loudnorm pass 2 (applying)..." >&2
  apply_loudnorm_2pass "$audio_source" "$output_file" "$process_chain" "$target_lra" \
    "$m_i" "$m_tp" "$m_lra" "$m_thresh"

  echo "Output written to: $output_file (DeepFilterNet atten=${dfn_atten_db}dB, 2-pass loudnorm)"
}

main "$@"
