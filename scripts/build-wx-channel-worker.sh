#!/usr/bin/env bash
set -euo pipefail

readonly UPSTREAM_URL="https://github.com/nobiyou/wx_channel.git"
readonly UPSTREAM_COMMIT="3dd74f0e21f7d9f6bdc5bec9338e433c57cbe8d0"
readonly SUNNYNET_URL="https://github.com/qtgolang/SunnyNet.git"
readonly SUNNYNET_COMMIT="8a58b8b80d850c10284be4495761ad3269525f8b"
readonly NFAPI_WIN32_SHA256="b6ad927ce7a5281f1b71be347b6ee4b920a8ef90f104c6a5cc56082fba0c3528"
readonly NFAPI_X64_SHA256="1d6f3487d3aa707b978e1a81f8e98250d334120b856b89780408eb98dbbd0910"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="${1:-$repo_root/dist}"
build_root="$(mktemp -d)"
trap 'rm -rf "$build_root"' EXIT

for command_name in git go python3 x86_64-w64-mingw32-gcc x86_64-w64-mingw32-g++; do
  command -v "$command_name" >/dev/null || {
    echo "missing build dependency: $command_name" >&2
    exit 1
  }
done

git clone --quiet "$UPSTREAM_URL" "$build_root/wx_channel"
git -C "$build_root/wx_channel" checkout --quiet "$UPSTREAM_COMMIT"
test "$(git -C "$build_root/wx_channel" rev-parse HEAD)" = "$UPSTREAM_COMMIT"

git clone --quiet "$SUNNYNET_URL" "$build_root/sunnynet"
git -C "$build_root/sunnynet" checkout --quiet "$SUNNYNET_COMMIT"
test "$(git -C "$build_root/sunnynet" rev-parse HEAD)" = "$SUNNYNET_COMMIT"

mkdir -p \
  "$build_root/wx_channel/pkg/sunnynet/Resource/nfapi/dll/win32" \
  "$build_root/wx_channel/pkg/sunnynet/Resource/nfapi/dll/x64"
cp "$build_root/sunnynet/src/Resource/nfapi/dll/win32/nfapi.dll" \
  "$build_root/wx_channel/pkg/sunnynet/Resource/nfapi/dll/win32/nfapi.dll"
cp "$build_root/sunnynet/src/Resource/nfapi/dll/x64/nfapi.dll" \
  "$build_root/wx_channel/pkg/sunnynet/Resource/nfapi/dll/x64/nfapi.dll"

printf '%s  %s\n' "$NFAPI_WIN32_SHA256" \
  "$build_root/wx_channel/pkg/sunnynet/Resource/nfapi/dll/win32/nfapi.dll" | shasum -a 256 -c -
printf '%s  %s\n' "$NFAPI_X64_SHA256" \
  "$build_root/wx_channel/pkg/sunnynet/Resource/nfapi/dll/x64/nfapi.dll" | shasum -a 256 -c -

python3 "$repo_root/scripts/patch-wx-channel-worker.py" "$build_root/wx_channel"
gofmt -w \
  "$build_root/wx_channel/internal/app/app.go" \
  "$build_root/wx_channel/internal/handlers/page_handler.go" \
  "$build_root/wx_channel/internal/handlers/script.go" \
  "$build_root/wx_channel/internal/handlers/video_handler.go" \
  "$build_root/wx_channel/internal/utils/sanitize.go" \
  "$build_root/wx_channel/internal/utils/sanitize_test.go" \
  "$build_root/wx_channel/pkg/sunnynet/SunnyNet/SunnyNet.go"

(
  cd "$build_root/wx_channel"
  go test ./internal/utils ./internal/cloud ./internal/config ./internal/websocket
  env \
    GOOS=windows \
    GOARCH=amd64 \
    CGO_ENABLED=1 \
    CC=x86_64-w64-mingw32-gcc \
    CXX=x86_64-w64-mingw32-g++ \
    CGO_CFLAGS='-D_WIN32_WINNT=0x0501 -std=gnu17' \
    CGO_CXXFLAGS='-D_WIN32_WINNT=0x0501 -std=gnu++17' \
    go build \
      -mod=mod \
      -ldflags="-w -s -extldflags '-static -Wl,--allow-multiple-definition'" \
      -o "$build_root/wx_channel_cloud_hardened.exe" \
      .
)

mkdir -p "$output_dir"
output_path="$output_dir/wx_channel_cloud_hardened_v5.6.9_share_v1.exe"
cp "$build_root/wx_channel_cloud_hardened.exe" "$output_path"
shasum -a 256 "$output_path"
