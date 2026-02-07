"""Built-in workflow templates for OmniAI.

Each template defines a sequence of steps that the workflow engine executes.
Step prompt_template fields may contain placeholders:
  {input}           — the user-supplied goal / input text
  {step_N_output}   — output of step at seq=N (1-indexed)
"""

from __future__ import annotations

from typing import Any

BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Research & Summarize",
        "description": "Decompose a topic, research each subtopic, then synthesize findings into a comprehensive summary.",
        "category": "research",
        "steps": [
            {
                "seq": 1,
                "type": "plan",
                "title": "Decompose topic",
                "prompt_template": (
                    "You are a research planner. The user wants to research the following topic:\n\n"
                    "{input}\n\n"
                    "Break this topic into 3-5 focused subtopics that together cover the subject comprehensively. "
                    "Return ONLY a numbered list of subtopics, one per line. No extra commentary."
                ),
            },
            {
                "seq": 2,
                "type": "execute",
                "title": "Research subtopics",
                "prompt_template": (
                    "You are a thorough researcher. The user is studying:\n\n"
                    "{input}\n\n"
                    "The subtopics to cover are:\n{step_1_output}\n\n"
                    "For each subtopic, write a detailed paragraph covering key facts, insights, and nuances. "
                    "Use clear headings for each subtopic."
                ),
            },
            {
                "seq": 3,
                "type": "synthesize",
                "title": "Synthesize findings",
                "prompt_template": (
                    "You are an expert writer. The user researched:\n\n"
                    "{input}\n\n"
                    "Here are the detailed findings:\n\n{step_2_output}\n\n"
                    "Synthesize these into a well-structured summary with an introduction, key findings, "
                    "and a conclusion. Be concise but thorough."
                ),
            },
        ],
    },
    {
        "name": "Blog Post Generation",
        "description": "Create a polished blog post: outline first, write sections, then polish the final draft.",
        "category": "writing",
        "steps": [
            {
                "seq": 1,
                "type": "plan",
                "title": "Create outline",
                "prompt_template": (
                    "You are a content strategist. Create a blog post outline for:\n\n"
                    "{input}\n\n"
                    "Include a compelling title, introduction hook, 3-5 main sections with brief descriptions, "
                    "and a conclusion. Format as a numbered outline."
                ),
            },
            {
                "seq": 2,
                "type": "execute",
                "title": "Write sections",
                "prompt_template": (
                    "You are a skilled blog writer. Write the full blog post based on this outline:\n\n"
                    "{step_1_output}\n\n"
                    "Original topic: {input}\n\n"
                    "Write each section with engaging prose, examples, and transitions between sections. "
                    "Use markdown formatting with headings."
                ),
            },
            {
                "seq": 3,
                "type": "synthesize",
                "title": "Polish final draft",
                "prompt_template": (
                    "You are an editor. Polish this blog post draft:\n\n"
                    "{step_2_output}\n\n"
                    "Improve flow, fix any inconsistencies, strengthen the introduction and conclusion, "
                    "and ensure the tone is engaging throughout. Return the final polished version."
                ),
            },
        ],
    },
    {
        "name": "Code Review",
        "description": "Analyze code by identifying areas of concern, examining each, then producing a structured review.",
        "category": "development",
        "steps": [
            {
                "seq": 1,
                "type": "plan",
                "title": "Identify review areas",
                "prompt_template": (
                    "You are a senior code reviewer. The user wants a code review of:\n\n"
                    "{input}\n\n"
                    "Identify 3-6 key areas to review (e.g., correctness, error handling, performance, "
                    "security, readability, architecture). List them as a numbered list with brief descriptions."
                ),
            },
            {
                "seq": 2,
                "type": "execute",
                "title": "Analyze each area",
                "prompt_template": (
                    "You are a senior code reviewer. Analyze this code:\n\n"
                    "{input}\n\n"
                    "Review areas identified:\n{step_1_output}\n\n"
                    "For each area, provide detailed analysis: what's good, what needs improvement, "
                    "and specific suggestions with code examples where applicable."
                ),
            },
            {
                "seq": 3,
                "type": "synthesize",
                "title": "Summary & recommendations",
                "prompt_template": (
                    "You are a senior code reviewer. Based on this analysis:\n\n"
                    "{step_2_output}\n\n"
                    "Create a structured code review summary with:\n"
                    "1. Overall assessment (brief)\n"
                    "2. Critical issues (must fix)\n"
                    "3. Suggestions (nice to have)\n"
                    "4. Positive highlights\n"
                    "5. Priority action items\n"
                    "Be concise and actionable."
                ),
            },
        ],
    },
    {
        "name": "Compare & Contrast",
        "description": "Compare items by identifying dimensions, analyzing each, then producing a comparison table.",
        "category": "analysis",
        "steps": [
            {
                "seq": 1,
                "type": "plan",
                "title": "Identify comparison dimensions",
                "prompt_template": (
                    "You are an analyst. The user wants to compare:\n\n"
                    "{input}\n\n"
                    "Identify 4-7 meaningful dimensions for comparison. "
                    "Return a numbered list of dimensions with brief descriptions of what each covers."
                ),
            },
            {
                "seq": 2,
                "type": "execute",
                "title": "Analyze dimensions",
                "prompt_template": (
                    "You are an analyst comparing:\n\n"
                    "{input}\n\n"
                    "Dimensions to analyze:\n{step_1_output}\n\n"
                    "For each dimension, provide a detailed comparison of all items. "
                    "Be specific with facts, pros, and cons for each item."
                ),
            },
            {
                "seq": 3,
                "type": "synthesize",
                "title": "Comparison summary",
                "prompt_template": (
                    "You are an analyst. Based on this comparison:\n\n"
                    "{step_2_output}\n\n"
                    "Create a structured summary with:\n"
                    "1. A markdown comparison table (dimensions as rows, items as columns)\n"
                    "2. Key differentiators\n"
                    "3. Recommendation (if applicable)\n"
                    "4. When to choose each option\n"
                    "Be objective and concise."
                ),
            },
        ],
    },
]


def get_builtin_templates() -> list[dict[str, Any]]:
    """Return all built-in workflow templates."""
    return BUILTIN_TEMPLATES
