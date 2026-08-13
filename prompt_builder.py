"""构造摘要 prompt 与信息图海报 prompt。"""


def _layout_desc(aspect: str) -> str:
    return {
        "square": "a square canvas, tall enough to fit several sections stacked vertically",
        "landscape": "a wide horizontal canvas",
        "portrait": "a vertical portrait canvas",
    }[aspect]


def build_summary_prompt(source_text: str) -> str:
    return f"""你是一名资深知识提炼助手。请阅读下面这段材料，把它提炼成一张"知识信息图海报"所需的全部文字内容。

要求：
1. 抓住核心论点，忠实于原文，不编造。
2. points 给出 3~6 个要点，每个 heading 是一个短标题（2~8 字），text 是一两句精炼说明（不超过 40 字）。
3. 标题和要点要有记忆点和冲击力，像社交媒体爆款知识卡片那样抓人，但保持准确。
4. 所有文字使用简体中文。
5. 只输出一个严格 JSON 对象，不要任何额外文字、注释或代码块标记。

JSON 结构如下：
{{
  "title": "主标题，一句话概括主题（不超过 16 字）",
  "subtitle": "副标题，一句话补充说明（不超过 24 字）",
  "points": [
    {{"heading": "要点标题1", "text": "要点说明1"}},
    {{"heading": "要点标题2", "text": "要点说明2"}},
    {{"heading": "要点标题3", "text": "要点说明3"}}
  ],
  "quote": "底部一句点睛引语或总结（不超过 20 字）"
}}

材料如下：
---
{source_text}
---"""


def _points_block(points) -> str:
    lines = []
    for i, p in enumerate(points, 1):
        heading = (p.get("heading") or "").strip()
        text = (p.get("text") or "").strip()
        lines.append(f"Point {i}: heading text \"{heading}\"; description text \"{text}\"")
    return "\n".join(lines)


STYLES = {
    "creative-long": (
        "Creative illustrated knowledge-card style, like a viral knowledge long-poster: warm light "
        "background (soft cream or pale gradient), hand-drawn doodle icons and cute line-art "
        "illustrations for each section (lightbulb, robot, cloud, chat bubble shapes), rounded card "
        "modules with playful borders, a decorated hand-lettered main title with an ornamental frame, "
        "soft harmonious accent colors (orange, blue, green on a light base), flowing arrows and "
        "dotted leader lines that guide the eye through the sections, high information density but "
        "clean and airy. Friendly, vivid, and highly shareable."
    ),
    "vaporwave": (
        "Vaporwave retro-futuristic aesthetic: dreamy pastel palette of neon pink, cyan and deep "
        "purple, a shimmering perspective grid floor receding into the distance, classical Greek "
        "statues and palm silhouettes as decorative elements, retro CRT glow, subtle scanlines and "
        "chromatic aberration on text, chrome and holographic gradient titles, floating clouds and "
        "stars, a synthwave sun glow on the horizon. Dreamy, nostalgic and high-impact."
    ),
    "modern-gradient": (
        "Premium modern tech aesthetic: soft diagonal gradient background, glassmorphism panels "
        "with subtle transparency and frosted blur, gentle 3D depth and soft shadows, a vivid but "
        "harmonious accent palette (indigo, violet, mint, amber), subtle floating geometric shapes "
        "and glowing dots. Polished, slightly futuristic, high-end."
    ),
    "editorial": (
        "Premium editorial magazine layout: bold oversized headline typography, strong visual "
        "hierarchy, generous white space, thin elegant dividing lines, a refined serif title paired "
        "with clean sans-serif body, sophisticated muted palette with one strong accent color "
        "(crimson or ink blue), subtle paper texture, timeless and professional."
    ),
    "handdrawn": (
        "Warm hand-drawn illustration style: sketchbook aesthetic with organic doodle borders, soft "
        "watercolor washes in pastel tones, playful hand-lettered title, cute line-art icons for each "
        "section, charmingly imperfect lines, cream paper background, cozy and inviting."
    ),
    "neon": (
        "Dark futuristic style: deep navy-black background with vibrant neon gradient accents "
        "(cyan, magenta, electric violet), glowing edges and light blooms, high-contrast luminous "
        "typography, sleek translucent panels on dark, cinematic and eye-catching."
    ),
    "vintage": (
        "Vintage retro style: aged paper texture in sepia and cream tones, classic serif typography "
        "reminiscent of old printed documents, ink-stamp circular seals, torn-paper edges, retro "
        "poster ornaments, muted mustard / brick / teal palette, nostalgic editorial charm."
    ),
    "swiss": (
        "Bold Swiss minimalist design: strict geometric grid, huge confident typography, large solid "
        "color blocks (strong red, black, white, yellow), precise alignment, zero ornamentation, "
        "instantly readable modern minimalism."
    ),
}


def build_poster_prompt(data: dict, aspect: str, style: str = "creative-long") -> str:
    """data: {title, subtitle, points:[{heading,text}...], quote}"""
    title = (data.get("title") or "知识信息图").strip()
    subtitle = (data.get("subtitle") or "").strip()
    quote = (data.get("quote") or "").strip()
    points = data.get("points") or []

    layout = _layout_desc(aspect)

    style_desc = STYLES.get(style, STYLES["creative-long"])

    prompt = f"""Create a striking knowledge infographic poster, {layout}, in the style described at the end. The poster must render the exact Chinese text provided below, word for word, with correct characters and no typos or omissions.

TOP AREA: A large main title on the first line: 「{title}」"""
    if subtitle:
        prompt += f"\nRight below the title, a smaller subtitle line: 「{subtitle}」"
    prompt += """

MIDDLE AREA: Organize the following key points into clearly separated numbered card modules stacked top to bottom. Each module has a numbered badge (1, 2, 3…), a small icon, a short bold heading, and a concise description below it. Give each module its own accent color, and connect the modules with subtle arrows or leader lines so the eye flows naturally from one to the next. Generous internal padding, so it reads like a designed infographic, not a wall of text:
"""
    prompt += _points_block(points)

    if quote:
        prompt += f"""

BOTTOM AREA: A single emphasized quote line in a callout card: 「{quote}」"""

    prompt += f"""

STYLE: {style_desc}

All text crisp and sharp, Chinese characters rendered correctly. No watermark, no frame borders beyond the canvas, no extra text beyond what is specified."""
    return prompt


NEGATIVE_PROMPT = (
    "blurry or garbled text, misspelled characters, duplicated or invented words, "
    "watermark, signature, frame border, low resolution, cluttered layout, "
    "oversaturated colors, deformed shapes, logo, extra text not in the prompt"
)


def build_summary_mindmap_prompt(source_text: str) -> str:
    return f"""你是一名知识结构梳理助手。请阅读下面这段材料，提炼成一张思维导图的结构。

要求：
1. topic 是中心主题，不超过 10 字。
2. branches 给出 4~6 个一级分支，每个 label 是分支名，不超过 8 字。
3. 每个分支下 children 有 1~3 个子节点，每个 label 不超过 14 字。
4. 忠实于原文，不编造，所有文字使用简体中文。
5. 只输出一个严格 JSON 对象，不要任何额外文字、注释或代码块标记。

JSON 结构如下：
{{
  "topic": "中心主题",
  "branches": [
    {{"label": "分支1", "children": [{{"label": "子节点1"}}, {{"label": "子节点2"}}]}},
    {{"label": "分支2", "children": [{{"label": "子节点3"}}]}}
  ]
}}

材料如下：
---
{source_text}
---"""


def build_mindmap_prompt(data: dict, aspect: str, style: str = "creative-long") -> str:
    """data: {topic, branches:[{label, children:[{label}]}]}"""
    topic = (data.get("topic") or "思维导图").strip()
    branches = data.get("branches") or []

    lines = [f"Central topic: 「{topic}」"]
    for i, b in enumerate(branches, 1):
        label = (b.get("label") or "").strip()
        kids = [(c.get("label") or "").strip() for c in (b.get("children") or [])]
        kid_part = "、".join(f"「{k}」" for k in kids) or "（无子节点）"
        lines.append(f"Branch {i}: 「{label}」 → child nodes: {kid_part}")
    node_text = "\n".join(lines)

    layout = _layout_desc(aspect)
    style_desc = STYLES.get(style, STYLES["creative-long"])

    prompt = f"""Create a beautiful mind map infographic, {layout}. Render the exact Chinese text provided below, word for word, with correct characters and no typos or omissions.

The central topic sits in a prominent rounded card at the center. From it, {len(branches)} main branches spread outward as smooth curved lines, each ending in a bold branch card with its own accent color. Under each branch, its child nodes hang as small rounded cards connected by thin lines.

Layout requirements: clear hierarchy, smooth non-overlapping curves, nodes never overlap, generous spacing, short readable text.

NODE CONTENT (render all exactly, no extra text):
{node_text}

STYLE: {style_desc}

All text crisp and sharp, Chinese characters rendered correctly. No watermark, no frame borders beyond the canvas, no extra text beyond what is specified."""
    return prompt
