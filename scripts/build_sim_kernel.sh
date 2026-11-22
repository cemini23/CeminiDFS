#!/usr/bin/env bash
# Build the scoring kernel and copy it next to the Python package.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
manifest="$root/rust/sim_kernel/Cargo.toml"
export PYO3_BUILD_EXTENSION_MODULE=1

cargo build --release --manifest-path "$manifest"

src="$root/rust/sim_kernel/target/release/libsim_kernel_rust.dylib"
dest="$root/src/ceminidfs/_sim_kernel_rust.so"
cp -f "$src" "$dest"
printf '%s\n' "$dest"
