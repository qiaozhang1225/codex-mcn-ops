from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ApiParamManifest:
    name: str
    param_type: str
    description: str


@dataclass
class PagingManifest:
    request_cursor_fields: list[str] = field(default_factory=list)
    response_cursor_fields: list[str] = field(default_factory=list)
    has_more_fields: list[str] = field(default_factory=list)


@dataclass
class ApiMethodManifest:
    key: str
    title: str
    group: str
    endpoint: str
    http_method: str
    content_type: str | None
    cost_weight: int
    requires_auth: bool
    requires_cookie: bool
    requires_extra_key: bool
    model_exposed: bool
    params: list[ApiParamManifest]
    returns: list[ApiParamManifest]
    paging: PagingManifest
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "external" / "mxnzp-douyin-pro-api.md"


def load_manifest_from_markdown(path: str | Path | None = None) -> list[ApiMethodManifest]:
    manifest_path = Path(path) if path else default_manifest_path()
    return parse_manifest(manifest_path.read_text(encoding="utf-8"))


def catalog_as_dict(methods: list[ApiMethodManifest]) -> dict[str, Any]:
    return {
        "method_count": len(methods),
        "model_exposed_count": len([method for method in methods if method.model_exposed]),
        "methods": [method.to_dict() for method in methods],
    }


def parse_manifest(markdown: str) -> list[ApiMethodManifest]:
    methods: list[ApiMethodManifest] = []
    heading_matches = list(re.finditer(r"(?m)^(##|###)\s+(.+)$", markdown))

    for index, match in enumerate(heading_matches):
        heading = match.group(2).strip()
        if not re.match(r"^\d+\.", heading):
            continue

        start = match.end()
        end = _find_section_end(markdown, heading_matches, index)
        body = markdown[start:end]

        endpoint = _extract_backtick_field(body, "接口地址")
        http_method = _extract_backtick_field(body, "请求方式")
        if not endpoint or not http_method:
            continue

        method_key = _method_key(endpoint)
        params, returns = _extract_params_and_returns(body)
        group = _classify_group(method_key, _group_before_heading(heading_matches, index))
        notes: list[str] = []
        if "Base64" in body or "base64" in body:
            notes.append("requires_base64_url")

        methods.append(
            ApiMethodManifest(
                key=method_key,
                title=re.sub(r"^\d+\.\s*", "", heading).strip(),
                group=group,
                endpoint=endpoint,
                http_method=http_method.upper(),
                content_type=_extract_backtick_field(body, "Content-Type"),
                cost_weight=_infer_cost_weight(body),
                requires_auth=True,
                requires_cookie=any(param.name == "cookie" for param in params),
                requires_extra_key=False,
                model_exposed=True,
                params=params,
                returns=returns,
                paging=_infer_paging(params, returns),
                notes=notes,
            )
        )
    return methods


def _find_section_end(markdown: str, heading_matches: list[re.Match[str]], index: int) -> int:
    for next_match in heading_matches[index + 1 :]:
        next_level = next_match.group(1)
        next_heading = next_match.group(2).strip()
        if re.match(r"^\d+\.", next_heading):
            return next_match.start()
        if next_level == "##" and not re.match(r"^\d+\.", next_heading):
            return next_match.start()
    return len(markdown)


def _group_before_heading(heading_matches: list[re.Match[str]], index: int) -> str:
    group = "core"
    for previous in heading_matches[:index]:
        if previous.group(1) == "##" and not re.match(r"^\d+\.", previous.group(2).strip()):
            group = _slugify_group(previous.group(2).strip())
    return group


def _extract_backtick_field(text: str, field_name: str) -> str | None:
    match = re.search(rf"\*\*{re.escape(field_name)}\*\*：\s*`([^`]+)`", text)
    return match.group(1).strip() if match else None


def _extract_params_and_returns(text: str) -> tuple[list[ApiParamManifest], list[ApiParamManifest]]:
    tables = _extract_tables(text)
    params = _extract_table_after(text, "请求参数")
    returns = _extract_table_after(text, "返回参数")
    if params or returns:
        if params and not returns:
            returns = _extract_return_tables_by_header(tables)
        return params, returns

    inferred_params: list[ApiParamManifest] = []
    inferred_returns: list[ApiParamManifest] = []
    seen_return_table = False
    for table in tables:
        if not table:
            continue
        header = table[0][0] if table[0] else ""
        parsed = _table_rows_to_params(table)
        if header in {"返回参数", "返回参数说明"}:
            inferred_returns.extend(parsed)
            seen_return_table = True
            continue
        if seen_return_table:
            inferred_returns.extend(parsed)
            continue
        inferred_params.extend(parsed)
    return inferred_params, inferred_returns


def _extract_return_tables_by_header(tables: list[list[list[str]]]) -> list[ApiParamManifest]:
    returns: list[ApiParamManifest] = []
    for table in tables:
        if table and table[0] and table[0][0] in {"返回参数", "返回参数说明"}:
            returns.extend(_table_rows_to_params(table))
    return returns


def _extract_table_after(text: str, anchor: str) -> list[ApiParamManifest]:
    anchor_match = re.search(
        rf"(?m)^(?:#{{2,6}}\s+{re.escape(anchor)}[^\n]*|- \*\*{re.escape(anchor)}(?:说明)?\*\*[^\n]*)$",
        text,
    )
    if not anchor_match:
        return []

    after = text[anchor_match.start() :]
    table_lines: list[str] = []
    started = False
    for line in after.splitlines():
        if line.strip().startswith("|"):
            started = True
            table_lines.append(line)
            continue
        if started:
            break
    return _table_rows_to_params([_split_table_line(line) for line in table_lines])


def _extract_tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            current.append(_split_table_line(line))
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _split_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_rows_to_params(table: list[list[str]]) -> list[ApiParamManifest]:
    params: list[ApiParamManifest] = []
    for cells in table:
        if len(cells) < 3:
            continue
        if cells[0] in {"名称", "返回参数", "返回参数说明"} or cells[0].startswith(":---"):
            continue
        name = cells[0].strip("` ")
        if not name:
            continue
        params.append(ApiParamManifest(name=name, param_type=cells[1], description=cells[2]))
    return params


def _infer_paging(params: list[ApiParamManifest], returns: list[ApiParamManifest]) -> PagingManifest:
    return PagingManifest(
        request_cursor_fields=[
            param.name for param in params if param.name in {"cursor", "offset", "search_id", "page"}
        ],
        response_cursor_fields=[
            param.name
            for param in returns
            if param.name in {"cursor", "max_cursor", "searchId", "search_id"}
        ],
        has_more_fields=[param.name for param in returns if param.name in {"hasMore", "has_more"}],
    )


def _infer_cost_weight(text: str) -> int:
    if "同接口18" in text or "1:5" in text:
        return 5
    if "n=6" in text:
        return 6
    if "n=5" in text:
        return 5
    if "n=2" in text or "1:2" in text:
        return 2
    if "1:n" in text:
        return 5
    return 1


def _classify_group(key: str, current_group: str) -> str:
    if key.startswith("billboard_"):
        return "billboard"
    if key in {"aweme_digs_interest", "user_fans_data"}:
        return "analytics"
    if key.startswith("user_mix") or key.startswith("user_series"):
        return "collection_series"
    if "search" in key:
        return "search"
    if key in {"comments", "child_comments", "user_post", "user_favorite_list"}:
        return "material_expansion"
    if key in {"detail", "detail_v3", "detail_v4", "share_link", "user_info", "user_info_dy_id"}:
        return "detail"
    if key == "video_to_text_v2":
        return "extract"
    return current_group


def _method_key(endpoint: str) -> str:
    prefix = "https://www.mxnzp.com/api/douyin_pro/"
    key = endpoint.replace(prefix, "")
    return key.strip("/").replace("/", "_").replace("-", "_")


def _slugify_group(value: str) -> str:
    if "榜单" in value:
        return "billboard"
    if "高级" in value:
        return "advanced"
    return "core"
