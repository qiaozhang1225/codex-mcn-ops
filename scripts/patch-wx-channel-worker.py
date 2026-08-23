from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise RuntimeError(f"expected exactly one patch target in {path}: {old[:80]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def patch_source(root: Path) -> None:
    script = root / "internal/handlers/script.go"
    replace_once(script, 'import (\n\t"bytes"\n', 'import (\n\t"bytes"\n\t"encoding/json"\n')
    replace_once(
        script,
        "\tkeepAliveJS     []byte\n\tversion         string\n",
        "\tkeepAliveJS     []byte\n\tlocalToken      string\n\tversion         string\n",
    )
    replace_once(
        script,
        "\t\tkeepAliveJS:     keepAliveJS,\n\t\tversion:         version,\n",
        "\t\tkeepAliveJS:     keepAliveJS,\n\t\tlocalToken:      cfg.SecretToken,\n\t\tversion:         version,\n",
    )
    replace_once(
        script,
        "func (h *ScriptHandler) buildInjectedScripts(path string) string {\n",
        "func (h *ScriptHandler) buildInjectedScripts(path string) string {\n"
        "\t// Define local authentication before api_client.js opens /ws/api. JSON\n"
        "\t// encoding prevents a configured token from breaking out of the script.\n"
        "\tlocalAuthScript := h.getLocalAuthScript()\n\n",
    )
    replace_once(
        script,
        "baseScripts := logPanelScript + mittScript",
        "baseScripts := localAuthScript + logPanelScript + mittScript",
    )
    replace_once(
        script,
        "// getPreloadScript 获取预加载FileSaver.js库的脚本\n",
        "func (h *ScriptHandler) getLocalAuthScript() string {\n"
        "\tencoded, err := json.Marshal(h.localToken)\n"
        "\tif err != nil {\n"
        "\t\treturn `<script>window.__WX_LOCAL_TOKEN__ = \"\";</script>`\n"
        "\t}\n"
        "\treturn fmt.Sprintf(`<script>window.__WX_LOCAL_TOKEN__ = %s;</script>`, encoded)\n"
        "}\n\n"
        "// getPreloadScript 获取预加载FileSaver.js库的脚本\n",
    )

    app = root / "internal/app/app.go"
    replace_once(app, 'Addr:    fmt.Sprintf(":%d", wsPort)', 'Addr:    fmt.Sprintf("127.0.0.1:%d", wsPort)')
    replace_once(
        app,
        'metricsAddr := fmt.Sprintf(":%d", app.Cfg.MetricsPort)',
        'metricsAddr := fmt.Sprintf("127.0.0.1:%d", app.Cfg.MetricsPort)',
    )

    sunny = root / "pkg/sunnynet/SunnyNet/SunnyNet.go"
    replace_once(
        sunny,
        'net.Listen("tcp", "0.0.0.0:"+strconv.Itoa(s.port))',
        'net.Listen("tcp", "127.0.0.1:"+strconv.Itoa(s.port))',
    )
    replace_once(
        sunny,
        'net.ResolveUDPAddr("udp", "0.0.0.0:"+strconv.Itoa(s.port))',
        'net.ResolveUDPAddr("udp", "127.0.0.1:"+strconv.Itoa(s.port))',
    )

    page = root / "internal/handlers/page_handler.go"
    replace_once(page, "health.HasKey, health.Href)", "health.HasKey, utils.SanitizeURLForLog(health.Href))")
    replace_once(page, 'utils.LogInfo("[页面访问] URL=%s", data.URL)', 'utils.LogInfo("[页面访问] URL=%s", utils.SanitizeURLForLog(data.URL))')

    video = root / "internal/handlers/video_handler.go"
    replace_once(
        video,
        'utils.LogInfo("[视频信息] ID=%s | 标题=%s | 作者=%s | 大小=%.2fMB | URL=%s | Key=%s | 分辨率=%s",\n\t\tvideoID, title, author, sizeMB, url, decryptKey, resolution)',
        'utils.LogInfo("[视频信息] ID=%s | 标题=%s | 作者=%s | 大小=%.2fMB | URL=%s | Key=<redacted> | 分辨率=%s",\n\t\tvideoID, title, author, sizeMB, utils.SanitizeURLForLog(url), resolution)',
    )
    replace_once(video, 'utils.LogInfo("[视频链接] URL=%s", videoURL)', 'utils.LogInfo("[视频链接] URL=%s", utils.SanitizeURLForLog(videoURL))')
    replace_once(video, 'utils.LogInfo("[页面链接] URL=%s", pageURL)', 'utils.LogInfo("[页面链接] URL=%s", utils.SanitizeURLForLog(pageURL))')

    (root / "internal/utils/sanitize.go").write_text(
        '''package utils

import (
\t"net/url"
\t"strings"
)

// SanitizeURLForLog retains only the origin and path. Signed query parameters
// and fragments must never be persisted in worker logs.
func SanitizeURLForLog(raw string) string {
\tparsed, err := url.Parse(strings.TrimSpace(raw))
\tif err != nil || parsed.Scheme == "" || parsed.Host == "" {
\t\treturn "<redacted-url>"
\t}
\tparsed.RawQuery = ""
\tparsed.ForceQuery = false
\tparsed.Fragment = ""
\tparsed.User = nil
\treturn parsed.String()
}
''',
        encoding="utf-8",
    )
    (root / "internal/utils/sanitize_test.go").write_text(
        '''package utils

import "testing"

func TestSanitizeURLForLog(t *testing.T) {
\tgot := SanitizeURLForLog("https://channels.weixin.qq.com/web/pages/home?pass_ticket=secret&exportkey=opaque#fragment")
\twant := "https://channels.weixin.qq.com/web/pages/home"
\tif got != want {
\t\tt.Fatalf("SanitizeURLForLog() = %q, want %q", got, want)
\t}
}

func TestSanitizeURLForLogRejectsNonAbsoluteURL(t *testing.T) {
\tif got := SanitizeURLForLog("pass_ticket=secret"); got != "<redacted-url>" {
\t\tt.Fatalf("SanitizeURLForLog() = %q", got)
\t}
}
''',
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the pinned wx_channel hardening overlay.")
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()
    patch_source(args.source_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
