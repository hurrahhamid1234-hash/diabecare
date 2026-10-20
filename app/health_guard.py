"""Safety rules around the chatbot. Plain Python, no extra packages.
These checks run BEFORE and AFTER the language model, so safety does not depend on a small model obeying a prompt."""
import re

EMERGENCY_TEXT = (
    "This could be an emergency. Please call your local emergency number now (112 in India) "
    "or go to the nearest hospital, or ask someone near you to help. Do not wait for an online answer.\n\n"
    "If the person is conscious and it may be low blood sugar, give 15 g of fast sugar (for example 3 glucose tablets "
    "or half a glass of juice) while help is on the way. Do not give food or drink to someone who is unconscious."
)

SELF_HARM_TEXT = (
    "I'm really sorry you are feeling this way, and I'm glad you said it. Please reach out right now to someone you trust, "
    "a local crisis helpline, or emergency services (112 in India). If you may act on these thoughts, please do not stay alone. "
    "You deserve support, and talking to a person can help."
)

_SELF_HARM = re.compile(r"suicid|kill myself|end my life|want to die|self[- ]?harm|hurt myself|no reason to live", re.I)
_EMERGENCY = re.compile(
    r"chest pain|pain in (my )?chest|(can'?t|cannot|can not) breathe|trouble breathing|difficulty breathing|"
    r"unconscious|passed out|not responding|seizure|convulsion|faint(ed|ing)|slurred speech|face (is )?droop|"
    r"one side (of (my|the) body )?(is )?(weak|numb)|overdos|severe (stomach|abdominal) pain|vomiting (and|with) .*(sugar|glucose)",
    re.I)

# a message must contain at least one of these (or be a short follow-up) to be answered
_HEALTH_WORDS = re.compile(
    r"diabet|sugar|glucose|insulin|hba1c|a1c|prediabet|carb|diet|food|eat|meal|breakfast|lunch|dinner|snack|fruit|rice|roti|bread|sweet|"
    r"drink|water|juice|alcohol|smok|exercise|workout|walk|yoga|gym|weight|obes|bmi|fat|sleep|stress|anxiety|depress|mental|mood|"
    r"blood|pressure|bp|cholesterol|heart|kidney|liver|eye|vision|foot|feet|skin|wound|nerve|tingl|numb|"
    r"symptom|pain|ache|fever|cold|cough|flu|infection|headache|dizz|tired|fatigue|weak|nause|vomit|thirst|urin|hungry|"
    r"doctor|medicine|medication|tablet|pill|metformin|dose|drug|vaccine|test|lab|report|checkup|health|healthy|disease|"
    r"hypo|hyper|ketone|pregnan|baby|child|elderly|vitamin|protein|salt|sodium|fibre|fiber|calorie|nutrition|hydrat|risk|prevent|cure|treat",
    re.I)

_GLUCOSE_NUM = re.compile(r"(?:sugar|glucose|reading|fasting|bgl|bs)\D{0,20}?(\d{2,3})(?!\d)|(?<!\d)(\d{2,3})\s*(?:mg/?dl)", re.I)


def emergency_reply(text: str):
    """Fixed reply when the message describes an emergency or self-harm, else None."""
    if _SELF_HARM.search(text):
        return SELF_HARM_TEXT
    if _EMERGENCY.search(text):
        return EMERGENCY_TEXT
    return None


def is_health_related(text: str, has_history: bool) -> bool:
    if _HEALTH_WORDS.search(text):
        return True
    # short follow-ups such as "why?", "tell me more", "how much?" inside an ongoing health chat
    return has_history and len(text.split()) <= 6


OFF_TOPIC_TEXT = "I can only help with health-related questions. Please ask me something about your health."


def glucose_note(text: str):
    """A fixed safety line when the user mentions a glucose number that is very low or very high."""
    m = _GLUCOSE_NUM.search(text)
    if not m:
        return None
    v = int(m.group(1) or m.group(2))
    if v < 20 or v > 700:
        return None
    if v < 54:
        return ("Safety note: a reading below 54 mg/dL is very low. Take 15 g of fast sugar now (3 glucose tablets or half a glass of juice), "
                "recheck in 15 minutes, and get urgent help if you feel confused or drowsy.")
    if v < 70:
        return ("Safety note: below 70 mg/dL is low. Take 15 g of fast sugar (3 glucose tablets or half a glass of juice), "
                "recheck in 15 minutes, and repeat if still low.")
    if v >= 300:
        return ("Safety note: 300 mg/dL or more is very high. Contact your doctor today. Seek urgent care if you have vomiting, "
                "stomach pain, fast breathing, drowsiness or confusion.")
    return None


_GREETING = re.compile(r"^\s*(hi+|hello+|hey+|hola|namaste|good (morning|afternoon|evening)|thanks?|thank you|ok(ay)?|bye)\W*$", re.I)
GREETING_TEXT = "Hello! I'm the DiabeCare assistant. You can ask me about diabetes, blood sugar, food, exercise, sleep or other health topics."


def greeting_reply(text: str):
    return GREETING_TEXT if _GREETING.match(text) else None