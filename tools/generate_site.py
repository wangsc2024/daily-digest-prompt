#!/usr/bin/env python3
"""Generate static website from knowledge base notes."""
import json
import re
from datetime import datetime
from pathlib import Path

# Load notes
with open('D:/Source/daily-digest-prompt/cache/full_notes.json', 'r', encoding='utf-8') as f:
    notes = json.load(f)

def slugify(text, note_id):
    """Generate ASCII-safe slug using ID prefix and English parts."""
    # Extract English/numbers only
    ascii_parts = re.findall(r'[a-zA-Z0-9]+', text)
    if ascii_parts:
        slug = '-'.join(ascii_parts[:4]).lower()
    else:
        slug = 'article'
    # Add short hash from ID for uniqueness
    short_id = note_id[:8]
    return f"{slug}-{short_id}"

def get_category_class(cat):
    mapping = {
        '佛學': 'buddhism',
        '思維方法': 'thinking',
        'AI技術': 'ai',
        'Claude_Code': 'claude',
        '其他': 'other'
    }
    return mapping.get(cat, 'other')

def get_category_display(cat):
    mapping = {'Claude_Code': 'Claude Code'}
    return mapping.get(cat, cat)

def markdown_to_html(text):
    """Simple markdown to HTML conversion."""
    if not text:
        return ''

    lines = text.split('\n')
    html = []
    in_list = False
    in_code = False
    list_type = 'ul'

    for line in lines:
        # Code blocks
        if line.startswith('```'):
            if in_code:
                html.append('</code></pre>')
                in_code = False
            else:
                html.append('<pre><code>')
                in_code = True
            continue

        if in_code:
            # Escape HTML in code
            line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html.append(line)
            continue

        # Headers
        if line.startswith('### '):
            if in_list:
                html.append(f'</{list_type}>')
                in_list = False
            html.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('## '):
            if in_list:
                html.append(f'</{list_type}>')
                in_list = False
            html.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('# '):
            if in_list:
                html.append(f'</{list_type}>')
                in_list = False
            html.append(f'<h1>{line[2:]}</h1>')
        # Unordered lists
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html.append('<ul>')
                in_list = True
                list_type = 'ul'
            html.append(f'<li>{process_inline(line[2:])}</li>')
        # Numbered lists
        elif re.match(r'^\d+\.\s', line):
            if not in_list:
                html.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = re.sub(r'^\d+\.\s', '', line)
            html.append(f'<li>{process_inline(content)}</li>')
        # Blockquote
        elif line.startswith('> '):
            if in_list:
                html.append(f'</{list_type}>')
                in_list = False
            html.append(f'<blockquote>{process_inline(line[2:])}</blockquote>')
        # Paragraphs
        elif line.strip():
            if in_list:
                html.append(f'</{list_type}>')
                in_list = False
            html.append(f'<p>{process_inline(line)}</p>')
        elif in_list:
            html.append(f'</{list_type}>')
            in_list = False

    if in_list:
        html.append(f'</{list_type}>')
    if in_code:
        html.append('</code></pre>')

    return '\n'.join(html)

def process_inline(text):
    """Process inline markdown elements."""
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text

# Group by category
categories = {}
for n in notes:
    cat = n['category']
    if cat not in categories:
        categories[cat] = []
    n['slug'] = slugify(n['title'], n['id'])
    categories[cat].append(n)

# Category order
category_order = ['佛學', '思維方法', 'AI技術', 'Claude_Code', '其他']

# Generate index.html
index_parts = ['''<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="個人知識庫：佛學、思維方法、AI技術與 Claude Code 研究">
  <title>知識庫 | Knowledge Base</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header>
    <div class="container">
      <a href="/" class="logo">知識庫</a>
      <nav>
        <a href="#buddhism">佛學</a>
        <a href="#thinking">思維方法</a>
        <a href="#ai">AI技術</a>
        <a href="#claude">Claude Code</a>
      </nav>
    </div>
  </header>

  <section class="hero">
    <div class="container">
      <h1>探索知識的邊界</h1>
      <p>彙整佛學智慧、思維方法論、AI 前沿技術與開發實踐</p>
    </div>
  </section>

  <main class="container">
''']

for cat in category_order:
    if cat not in categories or not categories[cat]:
        continue

    cat_class = get_category_class(cat)
    cat_display = get_category_display(cat)

    index_parts.append(f'''
    <section class="category-section" id="{cat_class}">
      <h2>{cat_display}</h2>
      <div class="article-list">
''')

    for n in categories[cat]:
        tags_html = ''.join([f'<span class="tag">{t}</span>' for t in n['tags'][:4]])
        index_parts.append(f'''
        <article class="article-card">
          <span class="category-badge category-{cat_class}">{cat_display}</span>
          <h3><a href="articles/{n['slug']}.html">{n['title']}</a></h3>
          <div class="tags">{tags_html}</div>
        </article>
''')

    index_parts.append('''
      </div>
    </section>
''')

index_parts.append(f'''
  </main>

  <footer>
    <div class="container">
      <p>Powered by RAG Knowledge Base | Last sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
  </footer>
</body>
</html>
''')

with open('D:/Source/knowledge/index.html', 'w', encoding='utf-8') as f:
    f.write(''.join(index_parts))

print('index.html generated')

# Generate article pages
articles_dir = Path('D:/Source/knowledge/articles')
articles_dir.mkdir(exist_ok=True)

for n in notes:
    cat_class = get_category_class(n['category'])
    cat_display = get_category_display(n['category'])
    content_html = markdown_to_html(n.get('contentText', ''))
    tags_html = ''.join([f'<span class="tag">{t}</span>' for t in n['tags']])

    article_html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{n['title']}">
  <title>{n['title']} | 知識庫</title>
  <link rel="stylesheet" href="../styles.css">
</head>
<body>
  <header>
    <div class="container">
      <a href="../" class="logo">知識庫</a>
      <nav>
        <a href="../#buddhism">佛學</a>
        <a href="../#thinking">思維方法</a>
        <a href="../#ai">AI技術</a>
        <a href="../#claude">Claude Code</a>
      </nav>
    </div>
  </header>

  <main class="container">
    <article>
      <div class="article-header">
        <span class="category-badge category-{cat_class}">{cat_display}</span>
        <h1>{n['title']}</h1>
        <div class="article-meta">
          <div class="tags">{tags_html}</div>
        </div>
      </div>

      <div class="article-content">
        {content_html}
      </div>

      <a href="../" class="back-link">← 返回首頁</a>
    </article>
  </main>

  <footer>
    <div class="container">
      <p>Powered by RAG Knowledge Base</p>
    </div>
  </footer>
</body>
</html>
'''

    with open(articles_dir / f"{n['slug']}.html", 'w', encoding='utf-8') as f:
        f.write(article_html)

    print(f"Generated: {n['slug']}.html")

print(f'\nTotal: {len(notes)} articles generated')

# Generate sync-log.json
sync_log = {
    "last_sync": datetime.now().isoformat(),
    "synced_notes": [
        {
            "id": n['id'],
            "title": n['title'],
            "slug": n['slug'],
            "category": n['category'],
            "hash": n.get('hash', '')
        }
        for n in notes
    ],
    "stats": {
        "total_articles": len(notes),
        "categories": {cat: len(items) for cat, items in categories.items()}
    }
}

with open('D:/Source/knowledge/sync-log.json', 'w', encoding='utf-8') as f:
    json.dump(sync_log, f, ensure_ascii=False, indent=2)

print('sync-log.json generated')
