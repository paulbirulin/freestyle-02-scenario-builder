#!/usr/bin/env python
"""Terminal CLI for the Freestyle-02 Scenario Builder pipeline."""
from __future__ import annotations
import argparse, asyncio, logging, os, sys, threading, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
os.environ.pop("ANTHROPIC_MODEL", None)
from src.orchestrator import ScenarioOrchestrator
from src.state.session import SessionManager
from src.utils import find_scenarios as _find_scenarios, fork_scenario, collect_source_files

# --- Colors ---
class C:
    RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
    CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"
    RED="\033[31m"; MAGENTA="\033[35m"; WHITE="\033[97m"

def cprint(c, t, end="\n"): print(f"{c}{t}{C.RESET}", end=end, flush=True)
def banner(t, c=C.CYAN):
    w = max(len(t)+4, 60)
    cprint(c+C.BOLD, "┌"+"─"*(w-2)+"┐")
    cprint(c+C.BOLD, "│ "+t.ljust(w-4)+" │")
    cprint(c+C.BOLD, "└"+"─"*(w-2)+"┘")
def sep(ch="─", w=60, c=C.DIM): cprint(c, ch*w)

# --- i18n ---
I18N = {
  "en": dict(banner="⚡ Scenario Builder — CLI", select_model="Select model:",
    m_auto="Auto (SDK default)", m_sonnet="Sonnet 4.5 (best)", m_haiku="Haiku 4.5 (fast)",
    choice="Choice", default="default", select_effort="Select effort:",
    comm_lang="Communication language:", scenario_lang="Scenario content language:",
    chat_lbl="Chat language", sc_lbl="Scenario language",
    avail="Available scenarios:", start_new="Start new (empty)", sel_sc="Select scenario",
    no_sc="No scenarios found.", sc_nf="Scenario not found!", model_lbl="Model", effort_lbl="Effort",
    loaded="{n} files from {name}", path_nf="Path not found:", session="Session", workspace="Workspace",
    describe="Describe what to do with this scenario:", hint="(e.g. 'improve', 'fix pronouns')",
    default_msg="Analyze and suggest improvements.", starting="Starting pipeline...", msg_lbl="Message",
    approve="Approve? (y/n):", your_ans="Your answer:", answered="Answered",
    gate_ok="Gate {id} approved", gate_no="Gate {id} rejected", yn="Type 'y' or 'n'",
    interrupted="Interrupted", error="Error", finished="Finished",
    time="Total time", steps="Steps", questions="Questions", gates="Gates",
    consist="Consistency", src_reg="Source register", bye="Bye!",
    found="Found", available="Available"),
  "ru": dict(banner="⚡ Конструктор сценариев — CLI", select_model="Выберите модель:",
    m_auto="Авто (SDK)", m_sonnet="Sonnet 4.5 (качество)", m_haiku="Haiku 4.5 (быстрая)",
    choice="Выбор", default="по умолч.", select_effort="Уровень усилий:",
    comm_lang="Язык общения:", scenario_lang="Язык сценария:",
    chat_lbl="Язык чата", sc_lbl="Язык сценария",
    avail="Доступные сценарии:", start_new="Новый (пустой)", sel_sc="Выберите сценарий",
    no_sc="Сценарии не найдены.", sc_nf="Сценарий не найден!", model_lbl="Модель", effort_lbl="Усилие",
    loaded="{n} файлов из {name}", path_nf="Путь не найден:", session="Сессия", workspace="Директория",
    describe="Опишите что сделать со сценарием:", hint="(напр. 'улучшить', 'исправить местоимения')",
    default_msg="Проанализировать и предложить улучшения.", starting="Запуск pipeline...", msg_lbl="Сообщение",
    approve="Одобрить? (y/n):", your_ans="Ваш ответ:", answered="Отвечено",
    gate_ok="Шлюз {id} одобрен", gate_no="Шлюз {id} отклонён", yn="Введите 'y' или 'n'",
    interrupted="Прервано", error="Ошибка", finished="Завершено",
    time="Время", steps="Шагов", questions="Вопросов", gates="Шлюзов",
    consist="Проверок", src_reg="Реестр", bye="Пока!",
    found="Найден", available="Доступные"),
  "de": dict(banner="⚡ Szenario-Builder — CLI", select_model="Modell wählen:",
    m_auto="Auto (SDK)", m_sonnet="Sonnet 4.5 (Qualität)", m_haiku="Haiku 4.5 (schnell)",
    choice="Auswahl", default="Standard", select_effort="Aufwand:",
    comm_lang="Kommunikationssprache:", scenario_lang="Szenario-Sprache:",
    chat_lbl="Chat-Sprache", sc_lbl="Szenario-Sprache",
    avail="Verfügbare Szenarien:", start_new="Neu (leer)", sel_sc="Szenario wählen",
    no_sc="Keine Szenarien.", sc_nf="Nicht gefunden!", model_lbl="Modell", effort_lbl="Aufwand",
    loaded="{n} Dateien aus {name}", path_nf="Pfad nicht gefunden:", session="Sitzung", workspace="Verzeichnis",
    describe="Was möchten Sie tun?", hint="(z.B. 'verbessern', 'korrigieren')",
    default_msg="Analysieren und verbessern.", starting="Pipeline startet...", msg_lbl="Nachricht",
    approve="Genehmigen? (y/n):", your_ans="Ihre Antwort:", answered="Beantwortet",
    gate_ok="Gate {id} genehmigt", gate_no="Gate {id} abgelehnt", yn="'y' oder 'n'",
    interrupted="Unterbrochen", error="Fehler", finished="Abgeschlossen",
    time="Gesamtzeit", steps="Schritte", questions="Fragen", gates="Gates",
    consist="Konsistenz", src_reg="Register", bye="Tschüss!",
    found="Gefunden", available="Verfügbar"),
  "tr": dict(banner="⚡ Senaryo Oluşturucu — CLI", select_model="Model seçin:",
    m_auto="Otomatik (SDK)", m_sonnet="Sonnet 4.5 (kalite)", m_haiku="Haiku 4.5 (hızlı)",
    choice="Seçim", default="varsayılan", select_effort="Çaba seviyesi:",
    comm_lang="İletişim dili:", scenario_lang="Senaryo dili:",
    chat_lbl="Sohbet dili", sc_lbl="Senaryo dili",
    avail="Mevcut senaryolar:", start_new="Yeni (boş)", sel_sc="Senaryo seçin",
    no_sc="Senaryo bulunamadı.", sc_nf="Bulunamadı!", model_lbl="Model", effort_lbl="Çaba",
    loaded="{name}: {n} dosya", path_nf="Yol bulunamadı:", session="Oturum", workspace="Dizin",
    describe="Ne yapmak istiyorsunuz?", hint="(örn. 'geliştir', 'düzelt')",
    default_msg="Analiz et ve öner.", starting="Pipeline başlıyor...", msg_lbl="Mesaj",
    approve="Onayla? (y/n):", your_ans="Cevabınız:", answered="Cevaplandı",
    gate_ok="Kapı {id} onaylandı", gate_no="Kapı {id} reddedildi", yn="'y' veya 'n'",
    interrupted="Kesildi", error="Hata", finished="Tamamlandı",
    time="Süre", steps="Adımlar", questions="Sorular", gates="Kapılar",
    consist="Tutarlılık", src_reg="Kayıt", bye="Hoşça kal!",
    found="Bulundu", available="Mevcut"),
  "he": dict(banner="⚡ בונה תרחישים — CLI", select_model="בחר מודל:",
    m_auto="אוטומטי (SDK)", m_sonnet="Sonnet 4.5 (איכות)", m_haiku="Haiku 4.5 (מהיר)",
    choice="בחירה", default="ברירת מחדל", select_effort="רמת מאמץ:",
    comm_lang="שפת תקשורת:", scenario_lang="שפת תרחיש:",
    chat_lbl="שפת צ׳אט", sc_lbl="שפת תרחיש",
    avail="תרחישים זמינים:", start_new="חדש (ריק)", sel_sc="בחר תרחיש",
    no_sc="לא נמצאו.", sc_nf="לא נמצא!", model_lbl="מודל", effort_lbl="מאמץ",
    loaded="{n} קבצים מ-{name}", path_nf="נתיב לא נמצא:", session="הפעלה", workspace="תיקייה",
    describe="מה לעשות עם התרחיש?", hint="(לדוגמה: 'שפר', 'תקן')",
    default_msg="נתח והצע שיפורים.", starting="מפעיל pipeline...", msg_lbl="הודעה",
    approve="לאשר? (y/n):", your_ans="תשובה:", answered="נענה",
    gate_ok="שער {id} אושר", gate_no="שער {id} נדחה", yn="הקלד y או n",
    interrupted="הופסק", error="שגיאה", finished="הושלם",
    time="זמן", steps="שלבים", questions="שאלות", gates="שערים",
    consist="עקביות", src_reg="רישום", bye="להתראות!",
    found="נמצא", available="זמין"),
}
T: dict = I18N["en"]

# --- Setup ---
SKILL_ROOT = Path(__file__).resolve().parent
SCENARIOS_DIR = SKILL_ROOT.parent.parent.parent / "SCENARIOS"
logging.basicConfig(level=logging.INFO, format=f"{C.DIM}%(asctime)s [%(name)s]{C.RESET} %(message)s")
logger = logging.getLogger("cli")
LANGS = {"ru":"🇷🇺 Русский","en":"🇺🇸 English","de":"🇩🇪 Deutsch","tr":"🇹🇷 Türkçe","he":"🇮🇱 עברית"}

def find_scenarios():
    return _find_scenarios(SCENARIOS_DIR)

# --- Spinner ---
class Spinner:
    """Animated spinner showing elapsed time during long operations."""
    _frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._label = ""
    def start(self, label=""):
        self.stop()
        self._label = label
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    def stop(self):
        if self._thread and self._thread.is_alive():
            self._stop.set()
            self._thread.join(timeout=1)
    def _run(self):
        t0 = time.monotonic()
        i = 0
        while not self._stop.wait(0.15):
            el = time.monotonic() - t0
            frame = self._frames[i % len(self._frames)]
            print(f"\r  {C.DIM}{frame} {self._label} ({el:.0f}s){C.RESET}  ", end="", flush=True)
            i += 1
        print(f"\r{' '*60}\r", end="", flush=True)

_spinner = Spinner()

# --- Callbacks ---
async def on_message(d):
    a,s,t = d.get("agent","?"), d.get("step",0), d.get("text","")
    if a=="system":
        if "⏳" in t: _spinner.start(t.split("⏳")[1].strip()[:40])
        if "✅" in t or "🤖" in t: _spinner.stop()
        cprint(C.YELLOW+C.BOLD, f"  ⚡ [{a}] step {s}: {t}")
    elif a=="ConsistencyChecker": cprint(C.MAGENTA, f"  🔍 [{a}] step {s}: {t[:200]}")
    else:
        _spinner.stop()
        cprint(C.CYAN, f"  💬 [{a}] step {s}:")
        for line in t.split("\n"): cprint(C.WHITE, f"     {line}")

async def on_gate(d):
    _spinner.stop()
    gid = d.get('gate_id', 0)
    if gid >= 0:
        pass  # gate_responder thread handles the display

async def on_question(d):
    _spinner.stop()
    cprint(C.MAGENTA+C.BOLD, "")
    banner(f"❓ {d.get('agent','?')}", C.MAGENTA)
    cprint(C.WHITE+C.BOLD, f"  {d.get('question','?')}")
    if d.get("context"): cprint(C.DIM, f"  {d['context']}")
    if d.get("options"): cprint(C.CYAN, f"  {', '.join(str(o) for o in d['options'])}")

async def on_step_change(d):
    _spinner.stop()
    cprint(C.GREEN+C.BOLD,""); sep("═",60,C.GREEN)
    cprint(C.GREEN+C.BOLD, f"  📋 Step {d.get('step',0)} → {d.get('agent','?')}"); sep("═",60,C.GREEN)
    _spinner.start(f"Step {d.get('step',0)}: {d.get('agent','?')}")

async def on_consistency(d):
    s = d.get("status","ok")
    c = {"ok":C.GREEN,"warning":C.YELLOW,"error":C.RED}.get(s,C.WHITE)
    i = {"ok":"✅","warning":"⚠️","error":"❌"}.get(s,"❓")
    cprint(c, f"  {i} Consistency step {d.get('step',0)}: {s.upper()}")

# --- Input threads ---
_stop_threads = threading.Event()

def gate_responder(orch):
    while not _stop_threads.is_set():
        time.sleep(0.5)
        for gid, gate in list(orch.state.gates.items()):
            if gate.decision.value == "pending" and gid not in orch._gate_decisions:
                is_consistency = gid < 0
                if is_consistency:
                    # Consistency check — different look
                    cprint(C.CYAN, f"\n  {'─'*50}")
                    cprint(C.CYAN+C.BOLD, f"  🔍 Consistency check (step {-gid})?")
                    cprint(C.CYAN, f"  {'─'*50}")
                    try: ans = input(f"  {C.CYAN}y/n: {C.RESET}").strip().lower()
                    except EOFError: ans = "n"
                    orch._gate_decisions[gid] = ans in ("y","yes","да")
                    if gid in orch._gate_events: orch._gate_events[gid].set()
                    if ans in ("y","yes","да"):
                        cprint(C.GREEN, f"  ✅ Consistency check запущен")
                    else:
                        cprint(C.DIM, f"  ⏭️ Пропущено")
                else:
                    # Regular gate — prominent yellow
                    cprint(C.YELLOW+C.BOLD, f"\n  {'═'*50}")
                    cprint(C.YELLOW+C.BOLD, f"  🔒 GATE {gid}: {gate.description}")
                    cprint(C.YELLOW+C.BOLD, f"  {'═'*50}")
                    while True:
                        try: ans = input(f"  {C.YELLOW}{T['approve']} {C.RESET}").strip().lower()
                        except EOFError: ans = "y"
                        if ans in ("y","yes","да"):
                            orch._gate_decisions[gid] = True
                            if gid in orch._gate_events: orch._gate_events[gid].set()
                            cprint(C.GREEN, f"  ✅ {T['gate_ok'].format(id=gid)}"); break
                        elif ans in ("n","no","нет"):
                            orch._gate_decisions[gid] = False
                            if gid in orch._gate_events: orch._gate_events[gid].set()
                            cprint(C.RED, f"  ❌ {T['gate_no'].format(id=gid)}"); break
                        else: cprint(C.DIM, f"  {T['yn']}")

def question_responder(orch):
    done: set[str] = set()
    while not _stop_threads.is_set():
        time.sleep(0.3)
        for q in orch.state.questions:
            if q.answer is None and q.question_id not in done:
                done.add(q.question_id)
                try: ans = input(f"\n  {C.MAGENTA}{T['your_ans']} {C.RESET}").strip()
                except EOFError: ans = "(no input)"
                if not ans: ans = "(empty)"
                q.answer = ans
                from datetime import datetime, timezone
                q.answered_at = datetime.now(timezone.utc)
                orch._question_answers[q.question_id] = ans
                if q.question_id in orch._question_events:
                    orch._question_events[q.question_id].set()
                cprint(C.GREEN, f"  ✅ {T['answered']}: {ans[:60]}")

# --- Pipeline ---
async def run_pipeline(args):
    global T
    banner(T["banner"], C.CYAN); print()
    models = {"auto":"","sonnet":"sonnet","haiku":"haiku"}
    efforts = ["low","medium","high","xhigh","max"]
    mid, eff = args.model, args.effort

    if not mid:
        cprint(C.WHITE+C.BOLD, T["select_model"])
        for i,(k,v) in enumerate([("auto",T["m_auto"]),("sonnet",T["m_sonnet"]),("haiku",T["m_haiku"])],1):
            cprint(C.CYAN, f"  {i}. {v}")
        ch = input(f"  {C.WHITE}{T['choice']} [1-3, {T['default']}=1]: {C.RESET}").strip()
        mid = {"1":"auto","2":"sonnet","3":"haiku"}.get(ch,"auto")

    if not eff:
        cprint(C.WHITE+C.BOLD, f"\n{T['select_effort']}")
        for i,e in enumerate(efforts):
            m = f" ← {T['default']}" if e=="high" else ""
            cprint(C.CYAN, f"  {i+1}. {e}{m}")
        ch = input(f"  {C.WHITE}{T['choice']} [1-5, {T['default']}=3]: {C.RESET}").strip()
        idx = int(ch)-1 if ch.isdigit() and 1<=int(ch)<=5 else 2
        eff = efforts[idx]

    mval = models.get(mid,"")
    cprint(C.GREEN, f"\n  {T['model_lbl']}: {mid} ({mval or 'auto'})")
    cprint(C.GREEN, f"  {T['effort_lbl']}: {eff}")

    lk = list(LANGS.keys())
    ul, sl = args.ui_lang, args.sc_lang
    if not ul:
        cprint(C.WHITE+C.BOLD, f"\n{T['comm_lang']}")
        for i,(k,v) in enumerate(LANGS.items(),1):
            m = f" ← {T['default']}" if k=="ru" else ""
            cprint(C.CYAN, f"  {i}. {v}{m}")
        ch = input(f"  {C.WHITE}{T['choice']} [1-{len(LANGS)}, {T['default']}=1]: {C.RESET}").strip()
        idx = int(ch)-1 if ch.isdigit() and 1<=int(ch)<=len(LANGS) else 0
        ul = lk[idx]
    if not sl:
        cprint(C.WHITE+C.BOLD, f"\n{T['scenario_lang']}")
        for i,(k,v) in enumerate(LANGS.items(),1):
            m = f" ← {T['default']}" if k=="ru" else ""
            cprint(C.CYAN, f"  {i}. {v}{m}")
        ch = input(f"  {C.WHITE}{T['choice']} [1-{len(LANGS)}, {T['default']}=1]: {C.RESET}").strip()
        idx = int(ch)-1 if ch.isdigit() and 1<=int(ch)<=len(LANGS) else 0
        sl = lk[idx]

    T = I18N.get(ul, I18N["en"])
    cprint(C.GREEN, f"  {T['chat_lbl']}: {LANGS.get(ul,ul)}")
    cprint(C.GREEN, f"  {T['sc_lbl']}: {LANGS.get(sl,sl)}")
    sep()

    sp = args.scenario_path
    sf: list[str] = []
    if not sp:
        scs = find_scenarios()
        if scs:
            cprint(C.WHITE+C.BOLD, f"\n{T['avail']}")
            for i,s in enumerate(scs,1): cprint(C.CYAN, f"  {i}. {s.display} ({s.file_count} files)")
            cprint(C.DIM, f"  0. {T['start_new']}")
            ch = input(f"\n  {C.WHITE}{T['sel_sc']} [0-{len(scs)}]: {C.RESET}").strip()
            if ch.isdigit() and 1<=int(ch)<=len(scs):
                sp = scs[int(ch)-1].path
                cprint(C.GREEN, f"  → {scs[int(ch)-1].display}")
        else: cprint(C.YELLOW, f"  {T['no_sc']}")

    # Fork: if existing scenario selected, clone it to a new directory
    if sp:
        sd = Path(sp)
        if sd.exists() and any(sd.iterdir()):
            from src.utils import suggest_fork_name
            suggested = suggest_fork_name(sd)
            cprint(C.CYAN+C.BOLD, f"\n  📋 Fork: {sd.name} → ?")
            cprint(C.DIM, f"  Оригинал останется без изменений.")
            cprint(C.CYAN, f"  Предлагаемое имя: {suggested}")
            custom = input(f"  {C.WHITE}Новое имя (Enter={suggested}): {C.RESET}").strip()
            try:
                result = fork_scenario(sd, custom_name=custom)
                sp = str(result.new_path)
                cprint(C.GREEN+C.BOLD, f"  ✅ Скопировано: {result.original_name} → {result.new_name}")
                cprint(C.DIM, f"  {result.new_path}")
            except FileExistsError as e:
                cprint(C.RED, f"  ❌ {e}"); return

    if sp:
        sd = Path(sp)
        if sd.exists():
            sf = collect_source_files(sd)
            cprint(C.GREEN, f"  {T['loaded'].format(n=len(sf), name=sd.name)}")
        else: cprint(C.RED, f"  {T['path_nf']} {sp}"); return

    sm = SessionManager()
    st = sm.create_session(source_files=sf, workspace_dir=sp or "")
    st.model_id, st.effort, st.ui_language, st.scenario_language = mval, eff, ul, sl
    sm.save(st)
    cprint(C.GREEN+C.BOLD, f"\n  {T['session']}: {st.session_id}")
    cprint(C.GREEN, f"  {T['workspace']}: {st.workspace_dir}"); sep()

    if args.message: um = args.message
    else:
        cprint(C.WHITE+C.BOLD, f"\n{T['describe']}")
        cprint(C.DIM, f"  {T['hint']}")
        um = input(f"  {C.WHITE}> {C.RESET}").strip()
        if not um: um = T["default_msg"]

    sep(); cprint(C.CYAN+C.BOLD, f"\n  {T['starting']}")
    cprint(C.DIM, f"  {T['msg_lbl']}: {um[:80]}"); print()

    orch = ScenarioOrchestrator(sm, st.session_id,
        on_message=on_message, on_gate=on_gate, on_question=on_question,
        on_consistency=on_consistency, on_step_change=on_step_change)

    # Threads use _stop_threads event (not orch._is_running)
    _stop_threads.clear()
    threading.Thread(target=gate_responder, args=(orch,), daemon=True).start()
    threading.Thread(target=question_responder, args=(orch,), daemon=True).start()

    t0 = time.monotonic()
    try: await orch.run(um)
    except KeyboardInterrupt: cprint(C.YELLOW, f"\n  ⏸️  {T['interrupted']}")
    except Exception as e: cprint(C.RED+C.BOLD, f"\n  ❌ {T['error']}: {e}"); logger.exception("err")
    _spinner.stop()
    _stop_threads.set()  # Signal threads to stop
    el = time.monotonic() - t0

    print(); sep("═",60,C.GREEN)
    st = sm.load(st.session_id)
    sc = {"completed":C.GREEN,"failed":C.RED,"paused":C.YELLOW}.get(st.status.value, C.WHITE)
    cprint(sc+C.BOLD, f"  {T['finished']}: {st.status.value.upper()}")
    cprint(C.DIM, f"  {T['time']}: {el:.1f}s ({el/60:.1f} min)")
    cprint(C.DIM, f"  {T['steps']}: {st.current_step}")
    cprint(C.DIM, f"  {T['questions']}: {len(st.questions)}")
    cprint(C.DIM, f"  {T['gates']}: {sum(1 for g in st.gates.values() if g.decision.value=='approved')}/{len(st.gates)}")
    cprint(C.DIM, f"  {T['consist']}: {len(st.consistency_reports)}")
    if st.source_register: cprint(C.DIM, f"  {T['src_reg']}: {len(st.source_register)} chars")
    sep("═",60,C.GREEN)

def main():
    global T
    p = argparse.ArgumentParser(description="Scenario Builder CLI", epilog="""
Examples:
  python cli.py                                       # Interactive
  python cli.py -s ERT-03 -M haiku -e low --ui-lang ru
  python cli.py -s ERT-03 --ui-lang en --sc-lang ru -m "fix pronouns" """)
    p.add_argument("--scenario","-s",default="")
    p.add_argument("--scenario-path","-p",default="")
    p.add_argument("--model","-M",choices=["auto","sonnet","haiku"],default="")
    p.add_argument("--effort","-e",choices=["low","medium","high","xhigh","max"],default="")
    p.add_argument("--ui-lang",default="",choices=["ru","en","de","tr","he"])
    p.add_argument("--sc-lang",default="",choices=["ru","en","de","tr","he"])
    p.add_argument("--message","-m",default="")
    a = p.parse_args()

    if a.ui_lang: T = I18N.get(a.ui_lang, I18N["en"])
    if a.scenario and not a.scenario_path:
        scs = find_scenarios()
        ms = [s for s in scs if a.scenario.lower() in s.name.lower()]
        if ms: a.scenario_path = ms[0].path; cprint(C.GREEN, f"  {T['found']}: {ms[0].display}")
        else: cprint(C.RED, f"  {T['sc_nf']} '{a.scenario}'"); sys.exit(1)

    if os.name == "nt": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try: asyncio.run(run_pipeline(a))
    except KeyboardInterrupt: cprint(C.YELLOW, f"\n  {T['bye']}")

if __name__ == "__main__": main()
