import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from less import digest

DUE = datetime(2026, 10, 8, 18, tzinfo=digest.ZoneInfo("Asia/Shanghai"))


class MailDocument(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.text = []
        self.links = []
        self.tags = []
        self.paragraphs = 0
        self.hidden = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag in {"head", "style"}:
            self.hidden = True
        if tag == "a":
            self.links.append(dict(attrs)["href"])
        if tag == "p":
            self.paragraphs += 1
        if not self.hidden:
            self.text.append(" ")

    def handle_endtag(self, tag):
        if tag == "head":
            self.hidden = False
        if not self.hidden:
            self.text.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)

    @property
    def readable(self):
        return " ".join("".join(self.text).split())


def sample_briefs():
    return [{
        "title": "排版测试样稿：" + "用 AI 整理研究资料、写作与团队协作的实际方法" * 3,
        "published_at": "2026-10-08",
        "what_happened": '第一段：保留 <script>alert("测试")</script> 与 & 特殊字符。\n'
                         "同一段的第二行。\n\n第二段：先整理资料，再核对原文。",
        "why_it_matters": "解决重复整理工作的问题。\n\n适用于有原始资料的知识工作者。",
        "our_take": "这是 Less 的判断，须与作者的观点分开。",
        "uncertainty": "效果来自作者自己的观察，不代表普遍效果。",
        "sources": [{
            "name": '原始来源：写作与研究 <实践> & "记录"',
            "published_at": "2026-10-08",
            "url": 'https://example.com/workflow?lang=zh&quote="test"',
        }, {
            "name": "补充来源与一段很长的连续标识" + "long-source-" * 20,
            "published_at": None,
            "url": "https://example.com/" + "long-path-" * 30,
        }],
    }, {
        "title": "排版测试样稿：一个有依据的观点",
        "published_at": None,
        "what_happened": "作者认为应先拆解任务，并给出自己的工作记录。",
        "why_it_matters": "为尝试新工具提供可复查的出发点。",
        "our_take": None,
        "uncertainty": None,
        "sources": [{"name": "观点原文", "published_at": None,
                     "url": "https://example.com/opinion"}],
    }]


def compact(value):
    return " ".join(value.split())


def test_email_keeps_full_content_and_escapes_untrusted_text():
    briefs = sample_briefs()
    reviews = ['候选待复核：<新进展> & "相似报道"。', "第二条待复核说明。"]
    plain, html = digest.render_digest("evening", DUE, briefs, reviews)
    document = MailDocument(html)
    assert not {"script", "img", "iframe", "link"}.intersection(document.tags)
    assert "&lt;script&gt;" in html
    assert document.paragraphs > 10
    position = 0
    for brief in briefs:
        for key in ("title", "what_happened", "why_it_matters", "our_take", "uncertainty"):
            if brief.get(key):
                assert brief[key] in plain
                text = compact(brief[key])
                position = document.readable.index(text, position) + len(text)
        for source in brief["sources"]:
            assert source["url"] in plain
            assert source["url"] in document.links
            assert source["name"] in document.readable
    for note in reviews:
        assert note in plain
        assert note in document.readable
    # Stripping presentation leaves the same complete, ordered reading content.
    unstyled = re.sub(r'<style>.*?</style>|\s(?:style|class)="[^"]*"', "", html, flags=re.S)
    assert MailDocument(unstyled).readable == document.readable


@pytest.mark.parametrize("mode", ["normal", "empty", "failure", "review"])
def test_email_mime_preserves_plain_and_html_parts(monkeypatch, mode):
    monkeypatch.setattr(digest, "settings", lambda: SimpleNamespace(
        mail_from="less@example.com", mail_to="reader@example.com"))
    briefs = sample_briefs() if mode == "normal" else []
    reviews = ["去重待复核：需要检查原报道与新增事实。"] if mode == "review" else None
    message = digest.build_email("evening", DUE, briefs, failure=mode == "failure",
                                 review_notes=reviews)
    decoded = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    plain = decoded.get_body(preferencelist=("plain",)).get_content()
    html = decoded.get_body(preferencelist=("html",)).get_content()
    expected = digest.FAILURE_NOTICE + "\n" if mode == "failure" else digest.render_digest(
        "evening", DUE, briefs, reviews)[0]
    assert plain == expected
    readable = MailDocument(html).readable
    assert "Less" in readable and "Read less. Know more." in readable
    assert "2026-10-08" in readable and "晚间" in readable
    if mode == "failure":
        assert digest.FAILURE_NOTICE in readable
    elif mode in {"empty", "review"}:
        assert "本轮没有值得保留的新内容。" in readable
        if reviews:
            assert reviews[0] in readable
    else:
        assert "本轮保留 2 条 Brief。" in readable
