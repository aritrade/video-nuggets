"""
Content simplifier that rewrites technical content using real-world analogies
a 6-year-old could understand.

Uses an LLM (Groq Llama-3 by default, Ollama for local dev) when available;
otherwise falls back to a deterministic analogy engine so the pipeline always
works at zero cost.
"""
import re

from app import llm
from app.services.content_parser import ContentSection, ParsedContent

SIMPLIFIER_PROMPT = """You are a world-class educator who explains complex IT infrastructure
concepts so that a 6-year-old could understand them. Rewrite the content using:

1. Simple, everyday language (no jargon without explanation)
2. Real-world analogies (e.g., "A cluster is like a team of friends who share toys")
3. Vivid, relatable comparisons (kitchens, playgrounds, libraries, mailboxes)
4. Short sentences and clear structure
5. One key idea at a time

RULES:
- Keep all factual information accurate
- Replace jargon with analogies BUT also mention the proper term in parentheses
- Use "imagine..." or "think of it like..." to introduce analogies
- Each section should be narration-ready (read aloud as a video script)
- Target approximately 60-90 words per section
- Make it engaging and fun to listen to

Rewrite the following technical content:

TITLE: {title}

CONTENT:
{content}

Respond with ONLY the simplified narration script. Do not add headers or metadata."""


# Plain-language analogies for common infrastructure jargon, used by the
# deterministic fallback (the LLM does this far more fluently when available).
_ANALOGIES = [
    (r"\bhyperconverged infrastructure\b|\bHCI\b", "one all-in-one box that does both the thinking and the remembering, instead of lots of separate boxes"),
    (r"\bclusters?\b", "a team of friends who share their toys so they can do bigger things together"),
    (r"\bnodes?\b", "a single building block, like one LEGO brick you can keep adding more of"),
    (r"\bhypervisor\b", "a careful babysitter that lets many pretend-computers share one real computer without fighting"),
    (r"\bvirtual machines?\b|\bVMs?\b", "a pretend computer that lives inside a real one"),
    (r"\bdistributed storage\b|\bstorage pool\b", "a giant shared toy box that every computer can reach into"),
    (r"\bAPI\b", "a doorway that lets one program politely ask another program to do something"),
    (r"\bscale[- ]out\b", "growing by adding more building blocks instead of buying one giant thing"),
    (r"\bredundan\w*\b|\breplicat\w*\b", "keeping more than one copy, so losing one is no big deal"),
    (r"\bself[- ]healing\b|\brebuilds?\b", "fixing itself quietly in the background, like a cut that scabs over on its own"),
    (r"\bmanagement plane\b|\bconsole\b", "a control tower where one person can see and steer everything at once"),
    (r"\bscheduler\b", "a fair teacher who decides whose turn it is so nobody is left out or overloaded"),
]


async def simplify_content(parsed: ParsedContent) -> ParsedContent:
    """Simplify all sections, via LLM when available else deterministically."""
    simplified_sections = []
    for section in parsed.sections:
        simplified_text = await _simplify_section(section)
        simplified_sections.append(ContentSection(
            title=section.title,
            body=simplified_text,
            key=section.key,
            subsections=section.subsections,
            images=section.images,
        ))
    return ParsedContent(
        title=parsed.title,
        sections=simplified_sections,
        source_type=parsed.source_type,
        raw_text=parsed.raw_text,
    )


async def _simplify_section(section: ContentSection) -> str:
    if not section.body.strip():
        return section.body

    if llm.llm_available():
        prompt = SIMPLIFIER_PROMPT.format(title=section.title, content=section.body)
        text = await llm.chat([{"role": "user", "content": prompt}], max_tokens=500)
        if text:
            return text

    return _deterministic_simplify(section)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


def _deterministic_simplify(section: ContentSection) -> str:
    sentences = _split_sentences(section.body)
    lead = " ".join(sentences[:3])
    topic = re.sub(r"[.:?!]+$", "", section.title.lower()).strip()

    analogy = None
    haystack = (section.title + " " + section.body)
    for pattern, phrase in _ANALOGIES:
        m = re.search(pattern, haystack, flags=re.IGNORECASE)
        if m:
            analogy = (m.group(0), phrase)
            break

    out = [f"Let's talk about {topic}."]
    if analogy:
        out.append(f"Think of {analogy[0]} like {analogy[1]}.")
    simple = re.sub(r"\butiliz(e|es|ing|ation)\b", "use", lead, flags=re.IGNORECASE)
    simple = re.sub(r"\bleverag(e|es|ing)\b", "use", simple, flags=re.IGNORECASE)
    simple = re.sub(r"\bin order to\b", "to", simple, flags=re.IGNORECASE)
    simple = re.sub(r"\bapproximately\b", "about", simple, flags=re.IGNORECASE)
    if simple:
        out.append(simple)
    out.append("And that's the big idea — simple building blocks working together.")

    narration = re.sub(r"\s+", " ", " ".join(out)).strip()
    words = narration.split()
    if len(words) > 95:
        narration = " ".join(words[:95]) + " …"
    return narration


def estimate_narration_duration(text: str, words_per_minute: int = 150) -> float:
    return (len(text.split()) / words_per_minute) * 60
