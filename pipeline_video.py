import os
import sys
import json
import subprocess
from openai import OpenAI
import requests
from pypdf import PdfReader
from PIL import Image
import io
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.environ.get("CARTESIA_VOICE_ID", "2a1938fe-6a4c-4fa0-86a7-dd585a5f7211")

if not NVIDIA_API_KEY or not CARTESIA_API_KEY:
    raise ValueError("Missing API keys! Set NVIDIA_API_KEY and CARTESIA_API_KEY in Railway variables.")

LANGUAGE_NAMES = {
    "en": "English", "ar": "Arabic", "fr": "French", "es": "Spanish",
    "de": "German", "pt": "Portuguese", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "hi": "Hindi", "tr": "Turkish",
}

def log(msg):
    print(msg)
    sys.stdout.flush()

# ============================================================================
# DATA STRUCTURES (Per Spec Section 14, 16, 34)
# ============================================================================

@dataclass
class PatternProfile:
    """Stores the abstract winning pattern (not the text itself)"""
    pattern_version: str
    macro_structure: List[str]  # opening, hook, intro, main, transition, action, reflection, closing
    content_progression: List[str]  # how ideas flow
    sentence_rhythm: Dict[str, Any]  # short/medium/long ratios, question frequency
    paragraph_rhythm: Dict[str, Any]  # sentences per paragraph
    transition_behavior: List[str]  # when/how transitions occur
    explanation_behavior: Dict[str, Any]
    instruction_behavior: Dict[str, Any]
    question_behavior: Dict[str, Any]
    reflection_behavior: Dict[str, Any]
    closing_behavior: Dict[str, Any]
    voiceover_behavior: Dict[str, Any]
    tone: str
    language_behavior: Dict[str, Any]
    content_type: str  # educational, tutorial, marketing, etc.

@dataclass
class ContentLock:
    """Locked source content that MUST be preserved"""
    content_type: str
    title: str
    topic: str
    main_idea: str
    key_points: List[str]
    steps: List[str]
    instructions: List[str]
    examples: List[str]
    exercises: List[str]
    questions: List[str]
    reflection: str
    cta: str
    important_terms: List[str]
    required_facts: List[str]
    numbers: List[str]
    names: List[str]

@dataclass
class ValidationResult:
    """Two-pass validation result (Per Spec Section 34)"""
    content_score: float  # 0-100
    pattern_score: float  # 0-100
    voiceover_score: float  # 0-100
    contamination_score: float  # 0 = good, 100 = bad
    repetition_score: float  # 0 = good, 100 = bad
    missing_content: List[str]
    unrelated_content: List[str]
    pattern_violations: List[str]
    repetition_issues: List[str]
    approved: bool
    feedback: str

# ============================================================================
# PHASE 1: PATTERN ANALYZER (Per Spec Sections 3-14)
# ============================================================================

class PatternAnalyzer:
    """Analyzes winning scripts to extract abstract patterns (not text)"""
    
    def __init__(self, client: OpenAI):
        self.client = client
    
    def analyze(self, winning_scripts: List[str], language: str = "en") -> Optional[PatternProfile]:
        """
        Analyzes multiple winning scripts to extract the underlying pattern.
        Returns a PatternProfile (abstract structure), NOT the text.
        """
        log(f"[PATTERN] Analyzing {len(winning_scripts)} winning scripts...")
        
        # Combine scripts for analysis
        scripts_text = "\n\n---SCRIPT SEPARATOR---\n\n".join(winning_scripts)
        
        prompt = f"""You are a PATTERN ANALYZER. Your job is NOT to copy text, but to extract the ABSTRACT WRITING PATTERN.

Analyze these winning scripts at multiple levels:

**WINNING SCRIPTS TO ANALYZE:**
{scripts_text}

**YOUR TASK:**

Extract the following pattern elements (be specific and structural, not textual):

1. MACRO STRUCTURE: What sections appear and in what order?
   Examples: opening, hook, introduction, context, main idea, explanation, transition, 
   practical section, examples, instructions, questions, reflection, takeaway, closing
   
2. CONTENT PROGRESSION: How does the script move from idea to idea?
   Example: introduces topic → explains why it matters → gives example → asks viewer to act → reflects

3. SENTENCE RHYTHM: 
   - What is the ratio of short (<10 words) vs medium (10-20) vs long (>20) sentences?
   - How often are questions used?
   - How often are commands/instructions used?
   - What is the punctuation rhythm?

4. PARAGRAPH RHYTHM:
   - How many sentences typically before a transition?
   - How are instructions separated?
   - How are questions isolated?

5. TRANSITION BEHAVIOR:
   - When do transitions occur?
   - What types of transitions are used?
   - How does the script move between ideas?

6. EXPLANATION BEHAVIOR:
   - How are concepts explained?
   - Are examples used before or after explanation?
   - Is theory or practice emphasized?

7. INSTRUCTION BEHAVIOR:
   - How are instructions delivered?
   - Are they direct commands or suggestions?
   - Are they simplified or detailed?

8. QUESTION BEHAVIOR:
   - Where do questions appear?
   - Are they rhetorical or reflective?
   - How many questions are typical?

9. REFLECTION BEHAVIOR:
   - How does the script transition to reflection?
   - What questions are asked?
   - How is closure created?

10. CLOSING BEHAVIOR:
    - How does the script end?
    - Is there a CTA?
    - What is the final emotional tone?
    - Sentence length at closing?

11. VOICEOVER BEHAVIOR:
    - Is it optimized for speaking?
    - Where are natural pauses?
    - Is language conversational?

12. TONE:
    - What is the overall tone?
    - Formal, casual, authoritative, friendly?

13. CONTENT TYPE:
    - Is this educational, tutorial, marketing, VSL, YouTube, other?

**OUTPUT FORMAT:**

Return ONLY valid JSON in this exact structure:

{{
  "pattern_version": "1.0",
  "macro_structure": ["opening", "hook", "introduction", ...],
  "content_progression": ["introduces topic", "explains why", ...],
  "sentence_rhythm": {{
    "short_sentence_ratio": 0.6,
    "medium_sentence_ratio": 0.3,
    "long_sentence_ratio": 0.1,
    "question_frequency": "high/medium/low",
    "instruction_frequency": "high/medium/low",
    "average_sentence_length": "short/medium/long"
  }},
  "paragraph_rhythm": {{
    "sentences_per_paragraph": "3-5",
    "transition_frequency": "every 2-3 paragraphs"
  }},
  "transition_behavior": ["short transition after intro", "pause before reflection", ...],
  "explanation_behavior": {{
    "method": "example-first or theory-first",
    "depth": "surface/deep",
    "uses_metaphors": true/false
  }},
  "instruction_behavior": {{
    "style": "direct/indirect",
    "complexity": "simple/detailed",
    "pressure": "high/low/none"
  }},
  "question_behavior": {{
    "location": "beginning/middle/end",
    "type": "rhetorical/reflective/actionable",
    "count": "1-3"
  }},
  "reflection_behavior": {{
    "transition": "how it transitions",
    "questions": "type of questions",
    "encouragement": "present/absent"
  }},
  "closing_behavior": {{
    "final_transition": "how it closes",
    "emotional_tone": "inspiring/calming/motivating",
    "sentence_length": "short/medium",
    "has_cta": true/false
  }},
  "voiceover_behavior": {{
    "natural_pauses": "frequent/occasional/rare",
    "conversational": true/false,
    "breathing_points": "every 2-3 sentences"
  }},
  "tone": "authoritative/friendly/inspiring/etc",
  "language_behavior": {{
    "formality": "formal/casual",
    "vocabulary": "simple/sophisticated",
    "repetition_for_emphasis": true/false
  }},
  "content_type": "educational/tutorial/marketing/VSL/YouTube/other"
}}

**CRITICAL RULES:**

1. DO NOT copy any actual text from the scripts.
2. DO NOT mention specific topics, examples, or exercises from the scripts.
3. Extract only the STRUCTURE and BEHAVIOR.
4. Be specific enough that another writer could recreate this pattern.
5. Focus on HOW it's written, not WHAT it says.

Return ONLY the JSON, no explanation."""

        try:
            completion = self.client.chat.completions.create(
                model="meta/llama-3.2-11b-vision-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Lower temperature for more structured output
                max_tokens=1500,
                timeout=300,
            )
            
            response = completion.choices[0].message.content.strip()
            
            # Parse JSON
            pattern_data = json.loads(response)
            
            # Convert to PatternProfile
            profile = PatternProfile(
                pattern_version=pattern_data.get("pattern_version", "1.0"),
                macro_structure=pattern_data.get("macro_structure", []),
                content_progression=pattern_data.get("content_progression", []),
                sentence_rhythm=pattern_data.get("sentence_rhythm", {}),
                paragraph_rhythm=pattern_data.get("paragraph_rhythm", {}),
                transition_behavior=pattern_data.get("transition_behavior", []),
                explanation_behavior=pattern_data.get("explanation_behavior", {}),
                instruction_behavior=pattern_data.get("instruction_behavior", {}),
                question_behavior=pattern_data.get("question_behavior", {}),
                reflection_behavior=pattern_data.get("reflection_behavior", {}),
                closing_behavior=pattern_data.get("closing_behavior", {}),
                voiceover_behavior=pattern_data.get("voiceover_behavior", {}),
                tone=pattern_data.get("tone", "neutral"),
                language_behavior=pattern_data.get("language_behavior", {}),
                content_type=pattern_data.get("content_type", "educational")
            )
            
            log(f"[PATTERN] Analysis complete. Type: {profile.content_type}")
            return profile
            
        except Exception as e:
            log(f"[ERROR] Pattern analysis failed: {e}")
            return None

# ============================================================================
# PHASE 2: CONTENT EXTRACTOR (Per Spec Sections 16-17)
# ============================================================================

class ContentExtractor:
    """Extracts and locks source content"""
    
    def __init__(self, client: OpenAI):
        self.client = client
    
    def extract(self, slide_text: str, language: str = "en") -> Optional[ContentLock]:
        """
        Extracts all important content from the source.
        Creates a CONTENT LOCK that must be preserved.
        """
        log(f"[CONTENT] Extracting and locking source content...")
        
        prompt = f"""You are a CONTENT EXTRACTOR. Your job is to extract ALL important information from source content.

**SOURCE CONTENT:**
{slide_text}

**YOUR TASK:**

Extract and lock the following elements:

1. CONTENT TYPE: What type is this? (educational, tutorial, marketing, VSL, YouTube, presentation, other)
2. TITLE: What is the main title/topic?
3. TOPIC: What specific subject is being taught/discussed?
4. MAIN IDEA: What is the core message?
5. KEY POINTS: List all important points (3-7)
6. STEPS: If there are steps, list them in order
7. INSTRUCTIONS: What must the viewer do?
8. EXAMPLES: What examples are provided?
9. EXERCISES: What exercises/activities are included?
10. QUESTIONS: What questions are asked?
11. REFLECTION: What reflection is requested?
12. CTA: Is there a call-to-action?
13. IMPORTANT TERMS: What specific terminology is used?
14. REQUIRED FACTS: What numbers, names, dates, facts must be preserved?
15. NUMBERS: Any specific numbers, durations, quantities?
16. NAMES: Any specific names (people, products, companies)?

**CRITICAL RULES:**

1. Extract EVERYTHING important. Do not summarize.
2. Preserve exact terminology, numbers, names.
3. Do not invent information not in the source.
4. Do not add information from your own knowledge.
5. If something is not in the source, leave it empty.
6. Be thorough and specific.

**OUTPUT FORMAT:**

Return ONLY valid JSON:

{{
  "content_type": "educational/tutorial/marketing/etc",
  "title": "exact title from source",
  "topic": "specific topic",
  "main_idea": "core message",
  "key_points": ["point 1", "point 2", ...],
  "steps": ["step 1", "step 2", ...],
  "instructions": ["instruction 1", ...],
  "examples": ["example 1", ...],
  "exercises": ["exercise 1", ...],
  "questions": ["question 1", ...],
  "reflection": "reflection question",
  "cta": "call to action",
  "important_terms": ["term 1", ...],
  "required_facts": ["fact 1", ...],
  "numbers": ["number 1", ...],
  "names": ["name 1", ...]
}}

Return ONLY the JSON, no explanation."""

        try:
            completion = self.client.chat.completions.create(
                model="meta/llama-3.2-11b-vision-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Very low for accurate extraction
                max_tokens=1500,
                timeout=300,
            )
            
            response = completion.choices[0].message.content.strip()
            content_data = json.loads(response)
            
            # Convert to ContentLock
            lock = ContentLock(
                content_type=content_data.get("content_type", "educational"),
                title=content_data.get("title", ""),
                topic=content_data.get("topic", ""),
                main_idea=content_data.get("main_idea", ""),
                key_points=content_data.get("key_points", []),
                steps=content_data.get("steps", []),
                instructions=content_data.get("instructions", []),
                examples=content_data.get("examples", []),
                exercises=content_data.get("exercises", []),
                questions=content_data.get("questions", []),
                reflection=content_data.get("reflection", ""),
                cta=content_data.get("cta", ""),
                important_terms=content_data.get("important_terms", []),
                required_facts=content_data.get("required_facts", []),
                numbers=content_data.get("numbers", []),
                names=content_data.get("names", [])
            )
            
            log(f"[CONTENT] Extraction complete. Topic: {lock.topic}")
            return lock
            
        except Exception as e:
            log(f"[ERROR] Content extraction failed: {e}")
            return None

# ============================================================================
# PHASE 3: CONTENT MAPPER (Per Spec Section 19)
# ============================================================================

class ContentMapper:
    """Maps source content onto winning pattern structure"""
    
    def map(self, pattern: PatternProfile, content: ContentLock) -> Dict[str, Any]:
        """
        Maps content elements to pattern positions.
        Example: Pattern has "opening → instruction → reflection → closing"
                 Content has "topic → exercise → question → takeaway"
                 Result: topic→opening, exercise→instruction, question→reflection, takeaway→closing
        """
        log(f"[MAPPER] Mapping content to pattern structure...")
        
        mapping = {
            "opening": {
                "content_element": "topic",
                "behavior": pattern.macro_structure[0] if pattern.macro_structure else "introduce"
            },
            "main_idea": {
                "content_element": "main_idea",
                "behavior": "explain"
            },
            "key_points": {
                "content_element": "key_points",
                "behavior": "elaborate"
            },
            "instructions": {
                "content_element": "instructions" if content.instructions else "exercises",
                "behavior": "direct_action"
            },
            "reflection": {
                "content_element": "reflection" if content.reflection else "questions",
                "behavior": "pause_and_reflect"
            },
            "closing": {
                "content_element": "cta" if content.cta else "main_idea",
                "behavior": "conclude"
            }
        }
        
        log(f"[MAPPER] Mapping complete. {len(mapping)} elements mapped.")
        return mapping

# ============================================================================
# PHASE 4: SCRIPT WRITER (Per Spec Sections 20-22)
# ============================================================================

class ScriptWriter:
    """Generates script using pattern + content (NOT copying text)"""
    
    def __init__(self, client: OpenAI):
        self.client = client
    
    def write(self, pattern: PatternProfile, content: ContentLock, mapping: Dict, language: str = "en") -> Optional[str]:
        """
        Writes script by adapting content to pattern.
        Does NOT copy winning script text.
        """
        log(f"[WRITER] Generating script using pattern + content...")
        
        # Convert pattern and content to JSON for the prompt
        pattern_json = json.dumps(asdict(pattern), indent=2)
        content_json = json.dumps(asdict(content), indent=2)
        
        prompt = f"""You are an expert SCRIPT WRITER. You write ORIGINAL scripts that follow a winning pattern.

**YOUR INPUTS:**

1. WINNING PATTERN (HOW to write):
{pattern_json}

2. SOURCE CONTENT (WHAT to say):
{content_json}

3. CONTENT MAPPING (where each element goes):
{json.dumps(mapping, indent=2)}

**YOUR TASK:**

Write an ORIGINAL script that:
- Uses the WINNING PATTERN structure and writing behavior
- Fills it with the SOURCE CONTENT (not the winning script's content)
- Sounds like the same skilled writer using the same successful formula
- Is completely ORIGINAL (not copied or paraphrased from winning script)
- Is optimized for voice-over (natural pauses, conversational, clear)

**CRITICAL RULES:**

1. **CONTENT RULES:**
   - The topic MUST be: {content.topic}
   - Include ALL key points: {', '.join(content.key_points[:3])}{'...' if len(content.key_points) > 3 else ''}
   - Include ALL exercises/instructions from source
   - Include the reflection from source
   - Preserve ALL numbers, names, terms exactly
   - DO NOT import winning script's topic, examples, or exercises

2. **PATTERN RULES:**
   - Follow the macro structure: {' → '.join(pattern.macro_structure[:5])}{'...' if len(pattern.macro_structure) > 5 else ''}
   - Match sentence rhythm: {pattern.sentence_rhythm.get('average_sentence_length', 'medium')} sentences
   - Use transitions like the pattern
   - Match the tone: {pattern.tone}
   - Create natural pauses for voice-over

3. **ORIGINALITY RULES:**
   - Do NOT copy sentences from winning script
   - Do NOT paraphrase winning script sentence-by-sentence
   - Do NOT use winning script's examples
   - Do NOT use winning script's topic
   - Write FRESH sentences using the pattern's behavior

4. **VOICE-OVER RULES:**
   - Short sentences (8-15 words average)
   - Natural pauses
   - Conversational language
   - Clear pronunciation
   - Direct address to viewer

**LANGUAGE:**
Write in {LANGUAGE_NAMES.get(language, language)}.

**LENGTH:**
Aim for 60-90 seconds of speech (approximately 150-220 words).

**OUTPUT:**

Write ONLY the finished script. No analysis, no notes, no explanation.
Just the final voice-over script ready for Cartesia."""

        try:
            completion = self.client.chat.completions.create(
                model="meta/llama-3.2-11b-vision-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
                timeout=300,
            )
            
            script = completion.choices[0].message.content.strip()
            log(f"[WRITER] Script generated ({len(script)} chars)")
            return script
            
        except Exception as e:
            log(f"[ERROR] Script writing failed: {e}")
            return None

# ============================================================================
# PHASE 5: VALIDATOR (Per Spec Sections 29-36)
# ============================================================================

class ScriptValidator:
    """Two-pass validation: Content + Pattern + Contamination + Repetition"""
    
    def __init__(self, client: OpenAI):
        self.client = client
    
    def validate(self, script: str, pattern: PatternProfile, content: ContentLock, language: str = "en") -> ValidationResult:
        """
        Validates script against all quality gates.
        Returns detailed validation result.
        """
        log(f"[VALIDATOR] Running two-pass validation...")
        
        prompt = f"""You are a STRICT SCRIPT VALIDATOR. You validate scripts against quality gates.

**INPUTS:**

1. GENERATED SCRIPT:
{script}

2. REQUIRED CONTENT (Content Lock):
{json.dumps(asdict(content), indent=2)}

3. WINNING PATTERN:
{json.dumps(asdict(pattern), indent=2)}

**VALIDATION CHECKS:**

## CONTENT VALIDATION (Score 0-100):
- Does script match topic: {content.topic}?
- Are key points included: {', '.join(content.key_points[:3])}?
- Are exercises/instructions included?
- Is reflection included (if in source)?
- Are numbers/names/terms preserved exactly?
- Was anything important omitted?
- Was unrelated information introduced?

## PATTERN VALIDATION (Score 0-100):
- Does opening behave like pattern: {pattern.macro_structure[0] if pattern.macro_structure else 'N/A'}?
- Does sentence rhythm match: {pattern.sentence_rhythm.get('average_sentence_length', 'N/A')}?
- Do transitions behave correctly?
- Does closing match pattern behavior?
- Is tone consistent: {pattern.tone}?

## CONTAMINATION VALIDATION (Score 0-100, where 0=good, 100=bad):
- Does script contain winning script's topic (NOT source topic)?
- Does script contain winning script's examples?
- Does script contain winning script's exercises?
- Is there topic leakage?

## REPETITION VALIDATION (Score 0-100, where 0=good, 100=bad):
- Are openings overly repetitive?
- Are transitions identical to previous scripts?
- Are sentence skeletons repeated?

## VOICEOVER VALIDATION (Score 0-100):
- Are sentences short enough (8-15 words)?
- Are there natural pauses?
- Is language conversational?
- Is it suitable for AI voice generation?

**OUTPUT FORMAT:**

Return ONLY valid JSON:

{{
  "content_score": 0-100,
  "pattern_score": 0-100,
  "voiceover_score": 0-100,
  "contamination_score": 0-100,
  "repetition_score": 0-100,
  "missing_content": ["missing item 1", ...],
  "unrelated_content": ["unrelated item 1", ...],
  "pattern_violations": ["violation 1", ...],
  "repetition_issues": ["issue 1", ...],
  "approved": true/false,
  "feedback": "detailed explanation of validation result"
}}

**QUALITY GATES:**

Script is APPROVED only if:
- content_score >= 90
- pattern_score >= 85
- voiceover_score >= 85
- contamination_score <= 10
- repetition_score <= 20

Return ONLY the JSON, no explanation."""

        try:
            completion = self.client.chat.completions.create(
                model="meta/llama-3.2-11b-vision-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Very low for consistent validation
                max_tokens=1000,
                timeout=300,
            )
            
            response = completion.choices[0].message.content.strip()
            validation_data = json.loads(response)
            
            result = ValidationResult(
                content_score=validation_data.get("content_score", 0),
                pattern_score=validation_data.get("pattern_score", 0),
                voiceover_score=validation_data.get("voiceover_score", 0),
                contamination_score=validation_data.get("contamination_score", 100),
                repetition_score=validation_data.get("repetition_score", 100),
                missing_content=validation_data.get("missing_content", []),
                unrelated_content=validation_data.get("unrelated_content", []),
                pattern_violations=validation_data.get("pattern_violations", []),
                repetition_issues=validation_data.get("repetition_issues", []),
                approved=validation_data.get("approved", False),
                feedback=validation_data.get("feedback", "")
            )
            
            if result.approved:
                log(f"[VALIDATOR] ✅ APPROVED (Content: {result.content_score}, Pattern: {result.pattern_score})")
            else:
                log(f"[VALIDATOR] ❌ FAILED: {result.feedback}")
            
            return result
            
        except Exception as e:
            log(f"[ERROR] Validation failed: {e}")
            return ValidationResult(
                content_score=0, pattern_score=0, voiceover_score=0,
                contamination_score=100, repetition_score=100,
                missing_content=["Validation error"], unrelated_content=[],
                pattern_violations=[], repetition_issues=[],
                approved=False, feedback=str(e)
            )

# ============================================================================
# MAIN PIPELINE FUNCTIONS
# ============================================================================

def pdf_to_images(pdf_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    reader = PdfReader(pdf_path)
    image_paths = []
    for i, page in enumerate(reader.pages):
        image_found = False
        for img in page.images:
            try:
                pil_image = Image.open(io.BytesIO(img.data))
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                image_path = f"{output_folder}/slide_{i+1:02d}.png"
                pil_image.save(image_path, "PNG")
                image_paths.append(image_path)
                log(f"[OK] Extracted: {image_path}")
                image_found = True
                break
            except Exception as e:
                log(f"[WARN] Failed to extract image {i+1}: {e}")
        if not image_found:
            log(f"[WARN] No image on page {i+1}, creating placeholder")
            img = Image.new('RGB', (1280, 720), color=(255, 255, 255))
            image_path = f"{output_folder}/slide_{i+1:02d}.png"
            img.save(image_path, "PNG")
            image_paths.append(image_path)
    return image_paths

def extract_text_from_slide(pdf_path, slide_index):
    try:
        reader = PdfReader(pdf_path)
        if slide_index < len(reader.pages):
            text = reader.pages[slide_index].extract_text()
            return text.strip() if text else f"Slide {slide_index + 1}"
    except Exception as e:
        log(f"[WARN] Could not extract text: {e}")
    return f"Slide {slide_index + 1}"

def generate_script(slide_text, language="en"):
    """
    MAIN SCRIPT GENERATION FUNCTION
    Implements the full Winning Pattern Intelligence Engine
    """
    log(f"[AI] Starting intelligent script generation for language: {language}...")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)
    
    # PHASE 1: Define winning pattern (in production, load from database)
    # For now, use the example pattern from your spec
    winning_scripts = [
        """مرحباً، وصلنا اليوم إلى اليوم الأول من التحدي.

اليوم سنبدأ بشيء بسيط.

شيء لا يحتاج إلى الكثير.

فقط بضع دقائق لنفسك.

والآن، خذي لحظة...

اجلسي بهدوء.

ثم اسألي نفسك:

ماذا أشعر الآن؟

لا تحاولي تغيير الإجابة.

فقط لاحظي."""
    ]
    
    # PHASE 2: Analyze pattern
    analyzer = PatternAnalyzer(client)
    pattern = analyzer.analyze(winning_scripts, language)
    
    if not pattern:
        log("[ERROR] Pattern analysis failed, using fallback")
        # Fallback to basic generation
        return generate_script_basic(slide_text, language)
    
    # PHASE 3: Extract content
    extractor = ContentExtractor(client)
    content = extractor.extract(slide_text, language)
    
    if not content:
        log("[ERROR] Content extraction failed")
        return None
    
    # PHASE 4: Map content to pattern
    mapper = ContentMapper()
    mapping = mapper.map(pattern, content)
    
    # PHASE 5: Write script
    writer = ScriptWriter(client)
    script = writer.write(pattern, content, mapping, language)
    
    if not script:
        log("[ERROR] Script writing failed")
        return None
    
    # PHASE 6: Validate (Two-pass)
    validator = ScriptValidator(client)
    validation = validator.validate(script, pattern, content, language)
    
    if not validation.approved:
        log(f"[ERROR] Validation failed: {validation.feedback}")
        # Try regeneration once
        log("[RETRY] Attempting regeneration...")
        script = writer.write(pattern, content, mapping, language)
        if script:
            validation = validator.validate(script, pattern, content, language)
            if not validation.approved:
                return None  # Second attempt also failed
    
    log(f"[OK] Script generated and validated (Content: {validation.content_score}, Pattern: {validation.pattern_score})")
    return script

def generate_script_basic(slide_text, language="en"):
    """Fallback basic generation if intelligent system fails"""
    log("[FALLBACK] Using basic script generation...")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)
    lang_name = LANGUAGE_NAMES.get(language, language)

    if language == "en":
        prompt = f"""You are an expert video scriptwriter. Slide content: "{slide_text}". 
        Write a short, engaging spoken script (60-80 words) in English. 
        Use clear, concise sentences. Natural pauses. Output ONLY the raw spoken text."""
    else:
        prompt = f"""أنت خبير في كتابة النصوص. محتوى الشريحة: "{slide_text}". 
        اكتب نصاً قصيراً وجذاباً (60-80 كلمة) باللغة العربية. 
        جمل واضحة ومختصرة. وقفات طبيعية. أخرج النص النهائي فقط."""

    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.2-11b-vision-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
            timeout=300,
        )
        script = completion.choices[0].message.content.strip()
        log("[OK] Script generated (basic)")
        return script
    except Exception as e:
        log(f"[ERROR] NVIDIA API error: {e}")
        return None

def generate_audio(script, output_path, language="en"):
    log(f"[AUDIO] STARTING audio generation for: {output_path}")
    log(f"[AUDIO] Language: {language}")
    log(f"[AUDIO] Script length: {len(script)} chars")
    log(f"[AUDIO] CARTESIA_API_KEY present: {bool(CARTESIA_API_KEY)}")
    log(f"[AUDIO] CARTESIA_VOICE_ID: {CARTESIA_VOICE_ID}")
    
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "Cartesia-Version": "2024-06-10",
        "X-API-Key": CARTESIA_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "model_id": "sonic-3",
        "voice": {"mode": "id", "id": CARTESIA_VOICE_ID},
        "output_format": {"container": "mp3", "bit_rate": 128000, "sample_rate": 44100},
        "transcript": script,
        "language": language,
    }
    
    try:
        log(f"[AUDIO] Sending request to Cartesia...")
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        log(f"[AUDIO] Cartesia response status: {response.status_code}")
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            file_size = os.path.getsize(output_path)
            log(f"[AUDIO] OK Audio saved: {output_path} (size: {file_size} bytes)")
            return output_path
        else:
            log(f"[AUDIO] ERROR Cartesia error: {response.status_code}")
            log(f"[AUDIO] Cartesia response body: {response.text[:500]}")
            return None
    except Exception as e:
        log(f"[AUDIO] ERROR Cartesia request failed: {type(e).__name__}: {e}")
        return None

def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 10.0

def create_clip(image_path, audio_path, duration, output_path):
    log(f"[CLIP] STARTING clip creation")
    log(f"[CLIP] Image exists: {os.path.exists(image_path)}")
    log(f"[CLIP] Audio exists: {os.path.exists(audio_path)}")
    log(f"[CLIP] Audio size: {os.path.getsize(audio_path) if os.path.exists(audio_path) else 0} bytes")
    log(f"[CLIP] Duration: {duration}s")
    
    duration = max(duration, 0.5)
    
    cmd = [
        "ffmpeg", 
        "-loop", "1", 
        "-i", image_path, 
        "-i", audio_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", 
        "-preset", "fast",
        "-crf", "20",
        "-t", str(duration + 0.5), 
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", "1",
        "-shortest", "-y", output_path
    ]
    
    log(f"[CLIP] Running FFmpeg command...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[CLIP] ERROR FFmpeg failed (return code: {result.returncode})")
        log(f"[CLIP] FFmpeg stderr: {result.stderr[:500]}")
        return None
    else:
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            log(f"[CLIP] OK Clip saved: {output_path} (size: {size} bytes)")
            return output_path
        else:
            log(f"[CLIP] ERROR FFmpeg reported success but file not found")
            return None

def concat_clips(clip_paths, output_path):
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    list_path = os.path.join(output_dir, "filelist.txt")
    
    log(f"[CONCAT] Creating filelist at: {list_path}")
    log(f"[CONCAT] Clips to concatenate: {clip_paths}")
    
    with open(list_path, "w") as f:
        for clip in clip_paths:
            abs_clip = os.path.abspath(clip)
            f.write(f"file '{abs_clip}'\n")
            log(f"[CONCAT] Added to list: {abs_clip}")
    
    cmd = [
        "ffmpeg", 
        "-f", "concat", 
        "-safe", "0", 
        "-i", list_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", "1",
        "-y", output_path
    ]
    
    log(f"[CONCAT] Running FFmpeg concat command...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        log(f"[ERROR] FFmpeg concat failed: {result.stderr}")
        if os.path.exists(list_path):
            os.remove(list_path)
        return False
    
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        log(f"[OK] Final video created: {output_path} (size: {file_size} bytes)")
        if os.path.exists(list_path):
            os.remove(list_path)
        return True
    else:
        log(f"[ERROR] FFmpeg reported success but file not found at: {output_path}")
        if os.path.exists(list_path):
            os.remove(list_path)
        return False

def phase_script(pdf_path, job_dir, language="en"):
    slides_folder = f"{job_dir}/slides"
    image_paths = pdf_to_images(pdf_path, slides_folder)
    scripts_data = []
    for i, img_path in enumerate(image_paths, 1):
        slide_text = extract_text_from_slide(pdf_path, i - 1)
        script = generate_script(slide_text, language=language)
        if not script:
            script = f"Let's take a look at slide {i}."
        scripts_data.append({"index": i, "image": img_path, "script": script})
    
    with open(f"{job_dir}/scripts.json", "w") as f:
        json.dump(scripts_data, f)
    log(f"[OK] {len(scripts_data)} scripts saved")
    return True

def phase_render(job_dir, output_video, language="en"):
    with open(f"{job_dir}/scripts.json", "r") as f:
        scripts_data = json.load(f)
    temp_audio_dir = f"{job_dir}/temp_audio"
    temp_clips_dir = f"{job_dir}/temp_clips"
    os.makedirs(temp_audio_dir, exist_ok=True)
    os.makedirs(temp_clips_dir, exist_ok=True)
    
    clips = []
    for entry in scripts_data:
        i, script, image_path = entry["index"], entry["script"], entry["image"]
        audio_path = f"{temp_audio_dir}/slide_{i:02d}.mp3"
        audio_file = generate_audio(script, audio_path, language=language)
        if not audio_file:
            continue
        duration = get_audio_duration(audio_file)
        clip_path = f"{temp_clips_dir}/clip_{i:02d}.mp4"
        clip = create_clip(image_path, audio_file, duration, clip_path)
        if clip:
            clips.append(clip)
        
    if not clips:
        log("[ERROR] No clips created")
        return False
    
    log(f"[RENDER] Starting concat of {len(clips)} clips...")
    success = concat_clips(clips, output_video)
    
    if success:
        log(f"[RENDER] Video generation completed successfully!")
    else:
        log(f"[RENDER] Video generation failed!")
    
    return success

def run_auto(pdf_path, output_video, job_dir, language="en"):
    if not phase_script(pdf_path, job_dir, language=language):
        return False
    return phase_render(job_dir, output_video, language=language)
