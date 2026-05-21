/**
 * 520 浪漫空间 — 自动分镜导演（打开即播，无需用户输入）
 */
(function () {
  "use strict";

  const CFG = window.LOVE520_CONFIG || {};
  const TO_NAME = (CFG.toName || "").trim() || "你";
  const FROM_NAME = (CFG.fromName || "永远爱你的人").trim();
  const VOW_LINES = CFG.vowLines || [
    "5 · 2 · 0",
    "是我爱你，最浪漫的谐音",
    "想把星河，都折进你眼里",
  ];
  const LETTER_LINES = CFG.letterLines || [
    "今天是 5 月 20 日，520。",
    "我爱你。",
    "520 快乐。",
  ];

  const FLOAT_PHRASES = [
    "520", "我爱你", "余生都是你", "心动", "温柔", "星河", "偏爱", "浪漫",
    "5·20", "♥", "想你", "告白", "今天也要开心",
  ];

  /** 各幕时长（毫秒），点击可提前切幕 */
  const ACT_DURATIONS = [4500, 9000, 8000, 14000, 0];

  const $ = (sel) => document.querySelector(sel);

  const SCENES = [
    $("#act-splash"),
    $("#act-vows"),
    $("#act-heart"),
    $("#act-letter"),
    $("#act-finale"),
  ];

  let fx;
  let actIndex = 0;
  let actTimer = null;
  let vowTimer = null;
  let typeTimer = null;
  let autoFireTimer = null;
  let vowIdx = 0;

  function setTodayLine() {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    const d = now.getDate();
    const el = $("#today-line");
    if (!el) return;
    el.textContent =
      d === 20 && m === 5
        ? `${y} 年 5 月 20 日 · 今天是 520`
        : `${y} 年 ${m} 月 ${d} 日 · 愿每一天都像 520 一样说爱你`;
  }

  function applyConfigText() {
    $("#letter-to").textContent = TO_NAME;
    $("#letter-from").textContent = FROM_NAME;
    $("#heart-caption").textContent =
      TO_NAME === "你" ? "把所有的爱，都给你" : `把所有的爱，都给 ${TO_NAME}`;
    $("#finale-sub").textContent =
      TO_NAME === "你" ? "愿你我，岁岁年年" : `${TO_NAME}，愿你我岁岁年年`;
  }

  function buildActDots() {
    const nav = $("#act-dots");
    nav.innerHTML = "";
    SCENES.forEach((_, i) => {
      const dot = document.createElement("span");
      dot.className = "act-dot";
      dot.dataset.act = String(i);
      nav.appendChild(dot);
    });
  }

  function updateDots() {
    document.querySelectorAll(".act-dot").forEach((d, i) => {
      d.classList.toggle("act-dot-active", i === actIndex);
      d.classList.toggle("act-dot-done", i < actIndex);
    });
  }

  function showAct(index) {
    actIndex = Math.max(0, Math.min(index, SCENES.length - 1));
    SCENES.forEach((el, i) => {
      el.classList.toggle("scene-active", i === actIndex);
    });
    updateDots();
    onActEnter(actIndex);
  }

  function clearActTimers() {
    if (actTimer) clearTimeout(actTimer);
    if (vowTimer) clearInterval(vowTimer);
    if (typeTimer) clearInterval(typeTimer);
    if (autoFireTimer) clearInterval(autoFireTimer);
    actTimer = vowTimer = typeTimer = autoFireTimer = null;
  }

  function scheduleNextAct() {
    if (actIndex >= SCENES.length - 1) return;
    const dur = ACT_DURATIONS[actIndex];
    if (dur <= 0) return;
    actTimer = setTimeout(() => nextAct(), dur);
  }

  function nextAct() {
    clearActTimers();
    if (actIndex < SCENES.length - 1) {
      showAct(actIndex + 1);
      scheduleNextAct();
    }
  }

  function ripple(x, y) {
    const el = document.createElement("span");
    el.className = "ripple";
    el.style.left = x + "px";
    el.style.top = y + "px";
    document.body.appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }

  function randomBurst() {
    if (!fx) return;
    const w = window.innerWidth;
    const h = window.innerHeight;
    fx.burst(w * (0.3 + Math.random() * 0.4), h * (0.25 + Math.random() * 0.45));
  }

  function spawnFloatWords() {
    const box = $("#float-words");
    box.innerHTML = "";
    for (let i = 0; i < 16; i++) {
      const li = document.createElement("li");
      li.textContent = FLOAT_PHRASES[i % FLOAT_PHRASES.length];
      li.style.left = 5 + Math.random() * 90 + "%";
      li.style.top = 8 + Math.random() * 78 + "%";
      li.style.animationDelay = -Math.random() * 8 + "s";
      li.style.animationDuration = 5 + Math.random() * 6 + "s";
      box.appendChild(li);
    }
  }

  /** 第二幕：逐句金句 */
  function runVows() {
    const lineEl = $("#vow-line");
    vowIdx = 0;
    const showLine = () => {
      if (vowIdx >= VOW_LINES.length) return;
      lineEl.classList.remove("vow-visible");
      void lineEl.offsetWidth;
      lineEl.textContent = VOW_LINES[vowIdx];
      lineEl.classList.add("vow-visible");
      vowIdx++;
      randomBurst();
    };
    showLine();
    vowTimer = setInterval(() => {
      if (vowIdx >= VOW_LINES.length) {
        clearInterval(vowTimer);
        vowTimer = null;
        return;
      }
      showLine();
    }, 1600);
  }

  /** 第四幕：情书打字 */
  function runLetter() {
    const full =
      (TO_NAME === "你" ? "" : `亲爱的 ${TO_NAME}：\n\n`) +
      LETTER_LINES.join("\n");
    const body = $("#letter-body");
    body.textContent = "";
    let idx = 0;
    typeTimer = setInterval(() => {
      if (idx <= full.length) {
        body.textContent = full.slice(0, idx);
        idx++;
      } else {
        clearInterval(typeTimer);
        typeTimer = null;
      }
    }, 48);
  }

  function onActEnter(index) {
    if (index === 0) {
      setTimeout(randomBurst, 600);
      setTimeout(randomBurst, 1800);
      setTimeout(fx?.celebrate, 2800);
    }
    if (index === 1) {
      runVows();
    }
    if (index === 2) {
      spawnFloatWords();
      randomBurst();
      autoFireTimer = setInterval(randomBurst, 2200);
    }
    if (index === 3) {
      runLetter();
      randomBurst();
    }
    if (index === 4) {
      $("#skip-hint").classList.add("skip-hint-hidden");
      fx?.celebrate();
    }
  }

  function initFX() {
    fx = new CanvasFX($("#fx-canvas"));
    fx.start();
  }

  function buildStars() {
    const box = $("#stars");
    const frag = document.createDocumentFragment();
    for (let i = 0; i < 80; i++) {
      const s = document.createElement("span");
      s.className = "star-dot";
      s.style.cssText = `
        left:${Math.random() * 100}%;
        top:${Math.random() * 100}%;
        animation-delay:${-Math.random() * 5}s;
        opacity:${0.2 + Math.random() * 0.8};
      `;
      frag.appendChild(s);
    }
    box.appendChild(frag);
  }

  function bind() {
    document.body.addEventListener("click", (e) => {
      if (actIndex >= SCENES.length - 1) {
        randomBurst();
        ripple(e.clientX, e.clientY);
        return;
      }
      ripple(e.clientX, e.clientY);
      randomBurst();
      nextAct();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Enter" || e.key === "ArrowRight") {
        e.preventDefault();
        nextAct();
      }
    });
  }

  function startShow() {
    setTodayLine();
    applyConfigText();
    buildActDots();
    showAct(0);
    scheduleNextAct();
  }

  document.addEventListener("DOMContentLoaded", () => {
    buildStars();
    initFX();
    bind();
    startShow();
  });
})();
