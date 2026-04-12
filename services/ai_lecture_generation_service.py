import os
import json
import re
from groq import Groq
from fastapi import HTTPException

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

DOMAIN_SOURCES = {
    "computer":       ["Cormen et al. – Introduction to Algorithms (MIT Press)", "Tanenbaum – Modern Operating Systems", "IEEE Xplore", "ACM Digital Library"],
    "database":       ["Ramakrishnan & Gehrke – Database Management Systems", "Silberschatz – Database System Concepts (7th ed.)", "ACM SIGMOD"],
    "machine learning": ["Bishop – Pattern Recognition and ML (Springer)", "Goodfellow – Deep Learning (MIT Press)", "ArXiv.org", "NeurIPS Proceedings"],
    "deep learning":  ["Goodfellow – Deep Learning (MIT Press)", "LeCun et al. – Nature 2015", "fast.ai Notes"],
    "ai":             ["Russell & Norvig – AI: A Modern Approach (4th ed.)", "Stanford CS221 Notes", "DeepMind Research Blog"],
    "software":       ["Pressman – Software Engineering (8th ed.)", "Clean Code – Robert C. Martin", "IEEE Software Journal"],
    "network":        ["Kurose & Ross – Computer Networking (8th ed.)", "Tanenbaum – Computer Networks (5th ed.)", "RFC Archive at IETF"],
    "security":       ["Stallings – Cryptography and Network Security", "Anderson – Security Engineering (3rd ed.)", "OWASP Foundation"],
    "data structure": ["Cormen – Introduction to Algorithms", "Sedgewick – Algorithms (4th ed.)", "Weiss – Data Structures and Algorithm Analysis"],
    "operating":      ["Tanenbaum – Modern Operating Systems (4th ed.)", "Silberschatz – Operating System Concepts", "Linux Kernel Docs"],
    "math":           ["Stewart – Calculus (8th ed.)", "Strang – Linear Algebra (MIT OCW)", "Wolfram MathWorld"],
    "physics":        ["Halliday, Resnick & Krane – Physics (5th ed.)", "The Feynman Lectures on Physics", "Physical Review Letters"],
    "default":        ["MIT OpenCourseWare", "Springer Academic", "Elsevier ScienceDirect", "Oxford Academic", "Cambridge University Press"],
}

MEDIA_LINKS = {
    "computer":       [{"title": "CS50 – Harvard Intro to CS", "url": "https://cs50.harvard.edu/x"}, {"title": "MIT OCW – Computer Science", "url": "https://ocw.mit.edu/search/?d=Electrical+Engineering+and+Computer+Science"}],
    "database":       [{"title": "CMU Database Group Lectures", "url": "https://www.youtube.com/@CMUDatabaseGroup"}, {"title": "Stanford DB Course – edX", "url": "https://www.edx.org/learn/databases"}],
    "machine learning": [{"title": "Andrew Ng – ML Specialization (Coursera)", "url": "https://www.coursera.org/specializations/machine-learning-introduction"}, {"title": "fast.ai – Practical Deep Learning", "url": "https://www.fast.ai"}, {"title": "Google ML Crash Course", "url": "https://developers.google.com/machine-learning/crash-course"}],
    "deep learning":  [{"title": "fast.ai Practical Deep Learning", "url": "https://www.fast.ai"}, {"title": "MIT 6.S191 – Intro to Deep Learning", "url": "http://introtodeeplearning.com"}],
    "ai":             [{"title": "Stanford CS221 – AI Principles", "url": "https://stanford-cs221.github.io/autumn2024/"}, {"title": "MIT 6.034 – Artificial Intelligence", "url": "https://ocw.mit.edu/courses/6-034-artificial-intelligence-fall-2010/"}],
    "software":       [{"title": "MIT Software Construction", "url": "https://ocw.mit.edu/courses/6-005-software-construction-spring-2016/"}, {"title": "Clean Code Principles", "url": "https://www.freecodecamp.org/news/clean-coding-for-beginners/"}],
    "network":        [{"title": "Kurose & Ross Companion Site", "url": "https://gaia.cs.umass.edu/kurose_ross/index.php"}, {"title": "Cisco Networking Academy", "url": "https://www.netacad.com"}],
    "data structure": [{"title": "Visualgo – Algorithm Visualizations", "url": "https://visualgo.net"}, {"title": "Princeton Algorithms (Coursera)", "url": "https://www.coursera.org/learn/algorithms-part1"}],
    "math":           [{"title": "3Blue1Brown – Visual Math", "url": "https://www.3blue1brown.com"}, {"title": "MIT OCW – Mathematics", "url": "https://ocw.mit.edu/search/?d=Mathematics"}],
    "physics":        [{"title": "The Feynman Lectures Online", "url": "https://www.feynmanlectures.caltech.edu"}, {"title": "MIT OCW – Physics", "url": "https://ocw.mit.edu/search/?d=Physics"}],
    "default":        [{"title": "MIT OpenCourseWare", "url": "https://ocw.mit.edu"}, {"title": "Coursera University Courses", "url": "https://www.coursera.org"}, {"title": "edX Academic Courses", "url": "https://www.edx.org"}],
}

def _pick(topic: str, lookup: dict) -> list:
    t = topic.lower()
    for key in lookup:
        if key in t:
            return lookup[key]
    return lookup["default"]


def generate_lecture_json(data) -> dict:
    trusted_sources = _pick(data.topic, DOMAIN_SOURCES)
    media_links     = _pick(data.topic, MEDIA_LINKS)
    additional      = getattr(data, "additional_instructions", "") or ""
    include_media   = getattr(data, "include_media", False)
    custom_sources  = getattr(data, "custom_sources", "") or ""

    if custom_sources:
        all_sources = [s.strip() for s in custom_sources.split(",") if s.strip()] + trusted_sources
    else:
        all_sources = trusted_sources

    adl        = additional.lower()
    depth      = "extremely detailed" if ("high detail" in adl or "detailed" in adl) else "university-level depth"
    prof_note  = additional if additional else "Produce a thorough, student-friendly academic lecture."

    prompt = f"""You are a world-class university professor and instructional designer.

Generate a COMPLETE lecture where each slide is self-contained and rich enough for students to study from independently.

PARAMETERS:
Topic: {data.topic}
Level: {data.course_level}
Slides: {data.pages_count}
Depth: {depth}

PROFESSOR INSTRUCTIONS (follow exactly):
{prof_note}

TRUSTED SOURCES:
{chr(10).join(f"* {s}" for s in all_sources[:5])}

SLIDE ORDER:
Slide 1: Title slide
Slide 2: Learning Objectives
Slide 3: Lecture Overview
Slides 4 to {data.pages_count - 2}: Core Content
Slide {data.pages_count - 1}: Summary and Key Takeaways
Slide {data.pages_count}: References

CRITICAL CONTENT STRUCTURE:
Each core content slide must use "points" — NOT separate "content" and "explanation" arrays.

Each point has:
- "headline": Short bold title (4-8 words max)
- "detail": 2-3 sentences explaining this specific headline in depth

This way each headline is immediately followed by its explanation — no separation.

Also include:
- "example": One concrete real-world example (3-4 sentences)
- "image_suggestion": Diagram description or null
- "speaker_notes": 3-4 sentences for professor delivery

Return ONLY valid JSON. Start with {{ end with }}. No markdown fences.

{{
  "slides": [
    {{
      "title": "Slide Title",
      "points": [
        {{
          "headline": "Short Bold Headline Here",
          "detail": "2-3 sentences explaining this headline in detail. Provide the mechanism, significance, and relationship to the topic."
        }},
        {{
          "headline": "Second Point Headline",
          "detail": "2-3 sentences explaining this second point in depth. Include why it matters and how it works."
        }},
        {{
          "headline": "Third Point Headline",
          "detail": "Explanation for the third point. Mention real implications or academic context."
        }}
      ],
      "example": "Concrete worked example: specific real-world illustration using a named system, algorithm, or experiment...",
      "image_suggestion": "Description of helpful educational diagram, or null",
      "speaker_notes": "What professor should emphasize. Connection to other slides. Question to ask students."
    }}
  ]
}}

RULES:
- Each slide must have 3-4 points (never more than 4 — keep slides focused and readable)
- Each "detail" must be 2-3 complete sentences minimum
- "example" must be concrete and specific (name real systems/companies/algorithms)
- Return EXACTLY {data.pages_count} slides
- Root JSON key MUST be "slides"
- No markdown, no text outside JSON"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a university lecture generator. "
                        "Output ONLY valid JSON starting with {{ ending with }}. "
                        "No markdown fences. No text before or after JSON. "
                        "Every slide MUST have: title, points (array of headline+detail objects), example, image_suggestion, speaker_notes."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.35,
            max_tokens=8000,
        )

        raw = completion.choices[0].message.content.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'^```\s*',     '', raw)
        raw = re.sub(r'\s*```$',     '', raw)

        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="AI did not return valid JSON. Please try again.")

        parsed = json.loads(match.group(0))

        # Normalize root key
        if "slides" not in parsed:
            for key in ["lecture", "presentation", "content", "data", "result"]:
                if key in parsed and isinstance(parsed[key], list):
                    parsed = {"slides": parsed[key]}
                    break
            else:
                for v in parsed.values():
                    if isinstance(v, list) and len(v) > 0:
                        parsed = {"slides": v}
                        break

        clean_slides = []
        for slide in parsed.get("slides", []):
            title = str(slide.get("title", "Slide")).strip()

            # Handle both new "points" format and old "content"+"explanation" format
            raw_points = slide.get("points", [])

            if raw_points and isinstance(raw_points, list):
                points = []
                for p in raw_points:
                    if isinstance(p, dict):
                        points.append({
                            "headline": str(p.get("headline", p.get("title", ""))).strip(),
                            "detail":   str(p.get("detail",   p.get("explanation", p.get("description", "")))).strip(),
                        })
                    elif isinstance(p, str):
                        # Fallback: AI returned strings instead of objects
                        points.append({"headline": p.strip(), "detail": ""})
            else:
                # Fallback: convert old content+explanation format
                old_content = slide.get("content", [])
                old_expl    = str(slide.get("explanation", "")).strip()
                if isinstance(old_content, str): old_content = [old_content]
                # Split explanation into sentences roughly per bullet
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', old_expl) if s.strip()]
                points = []
                for i, bullet in enumerate(old_content):
                    detail = sentences[i] if i < len(sentences) else ""
                    points.append({"headline": str(bullet).strip(), "detail": detail})

            # Normalize example
            example = slide.get("example", "")
            if isinstance(example, list): example = " ".join(str(e) for e in example)
            example = str(example).strip()

            # Normalize image suggestion
            img = slide.get("image_suggestion")
            if img and str(img).lower() in ("null", "none", "n/a", ""): img = None

            clean_slides.append({
                "title":            title,
                "points":           points,
                "example":          example,
                "image_suggestion": img,
                "speaker_notes":    str(slide.get("speaker_notes", "")).strip(),
            })

        # Append media resources slide if requested
        if include_media and clean_slides:
            media_points = [
                {"headline": l["title"], "detail": l["url"]}
                for l in media_links[:4]
            ]
            clean_slides.append({
                "title":         "Further Learning & Academic Resources",
                "points":        media_points,
                "example":       f"Visit MIT OpenCourseWare (ocw.mit.edu) for free university-level course materials on {data.topic} and related subjects.",
                "image_suggestion": None,
                "speaker_notes": f"Direct students to these resources for self-study and exam preparation on {data.topic}.",
            })

        if not clean_slides:
            raise HTTPException(status_code=500, detail="AI returned empty slides. Please try again.")

        return {"slides": clean_slides}

    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {e}. Try again.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))