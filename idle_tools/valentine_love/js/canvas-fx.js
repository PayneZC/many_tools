/**
 * 520 画布特效：心形粒子、飘落花瓣、烟花与点击星屑
 */
(function (global) {
  "use strict";

  const COLORS = ["#ff4d8d", "#ff8fab", "#ffd166", "#7df9ff", "#c77dff", "#ff6bcb"];

  /** 随机区间 */
  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  /** HSL 转 CSS 颜色字符串 */
  function hsl(h, s, l) {
    return `hsl(${h}, ${s}%, ${l}%)`;
  }

  class Particle {
    constructor(w, h, opts = {}) {
      this.reset(w, h, opts);
    }

    reset(w, h, opts) {
      this.x = opts.x ?? rand(0, w);
      this.y = opts.y ?? rand(0, h);
      this.vx = opts.vx ?? rand(-0.5, 0.5);
      this.vy = opts.vy ?? rand(-0.8, -0.15);
      this.life = opts.life ?? rand(120, 220);
      this.maxLife = this.life;
      this.size = opts.size ?? rand(3, 10);
      this.color = opts.color ?? COLORS[(Math.random() * COLORS.length) | 0];
      this.type = opts.type ?? (Math.random() < 0.5 ? "heart" : "petal");
      this.wobble = rand(0, Math.PI * 2);
    }

    update(w, h, t) {
      this.x += this.vx + Math.sin(t * 0.02 + this.wobble) * 0.15;
      this.y += this.vy;
      if (this.type === "petal") {
        this.vy += 0.03;
        this.vx += Math.sin(t * 0.03 + this.x * 0.01) * 0.02;
      } else {
        this.vy += 0.015;
      }
      this.life--;
      if (this.life <= 0 || this.y > h + 30) {
        this.reset(w, h, { y: h + 10, vy: rand(-1.2, -0.3), life: rand(140, 240) });
      }
      if (this.x < -20) this.x = w + 10;
      if (this.x > w + 20) this.x = -10;
    }

    draw(ctx) {
      const a = Math.min(1, this.life / this.maxLife);
      ctx.save();
      ctx.globalAlpha = a * 0.85;
      ctx.fillStyle = this.color;
      if (this.type === "heart") {
        drawHeart(ctx, this.x, this.y, this.size);
      } else {
        ctx.beginPath();
        ctx.ellipse(this.x, this.y, this.size * 0.5, this.size, this.wobble, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }
  }

  /** 绘制简化心形 */
  function drawHeart(ctx, x, y, s) {
    const topCurveHeight = s * 0.3;
    ctx.beginPath();
    ctx.moveTo(x, y + topCurveHeight);
    ctx.bezierCurveTo(x, y, x - s, y, x - s, y + topCurveHeight);
    ctx.bezierCurveTo(x - s, y + (s + topCurveHeight) / 2, x, y + (s + topCurveHeight) / 2, x, y + s);
    ctx.bezierCurveTo(x, y + (s + topCurveHeight) / 2, x + s, y + (s + topCurveHeight) / 2, x + s, y + topCurveHeight);
    ctx.bezierCurveTo(x + s, y, x, y, x, y + topCurveHeight);
    ctx.closePath();
    ctx.fill();
  }

  class Spark {
    constructor(x, y, hue) {
      this.x = x;
      this.y = y;
      const ang = rand(0, Math.PI * 2);
      const spd = rand(2, 9);
      this.vx = Math.cos(ang) * spd;
      this.vy = Math.sin(ang) * spd;
      this.life = rand(35, 65);
      this.maxLife = this.life;
      this.size = rand(1.5, 4);
      this.color = hue != null ? hsl(hue, 90, 65) : COLORS[(Math.random() * COLORS.length) | 0];
      this.gravity = 0.08;
    }

    update() {
      this.vx *= 0.98;
      this.vy *= 0.98;
      this.vy += this.gravity;
      this.x += this.vx;
      this.y += this.vy;
      this.life--;
    }

    draw(ctx) {
      const a = this.life / this.maxLife;
      ctx.save();
      ctx.globalAlpha = a;
      ctx.fillStyle = this.color;
      ctx.shadowBlur = 8;
      ctx.shadowColor = this.color;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  class Firework {
    constructor(x, y, targetY) {
      this.x = x;
      this.y = y;
      this.vy = -rand(10, 14);
      this.targetY = targetY ?? y * rand(0.25, 0.45);
      this.exploded = false;
      this.hue = rand(0, 360);
      this.trail = [];
    }

    update(sparks) {
      if (!this.exploded) {
        this.trail.push({ x: this.x, y: this.y });
        if (this.trail.length > 12) this.trail.shift();
        this.y += this.vy;
        this.vy += 0.22;
        if (this.vy >= -1 || this.y <= this.targetY) {
          this.explode(sparks);
        }
      }
    }

    explode(sparks) {
      this.exploded = true;
      const n = 64 + ((Math.random() * 32) | 0);
      for (let i = 0; i < n; i++) {
        sparks.push(new Spark(this.x, this.y, this.hue + rand(-20, 20)));
      }
    }

    draw(ctx) {
      if (this.exploded) return;
      ctx.save();
      for (let i = 0; i < this.trail.length; i++) {
        const p = this.trail[i];
        ctx.globalAlpha = (i / this.trail.length) * 0.6;
        ctx.fillStyle = hsl(this.hue, 90, 70);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(this.x, this.y, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  /** 心形轨迹光点 */
  function heartPoint(t, scale, cx, cy) {
    const x = 16 * Math.pow(Math.sin(t), 3);
    const y =
      13 * Math.cos(t) -
      5 * Math.cos(2 * t) -
      2 * Math.cos(3 * t) -
      Math.cos(4 * t);
    return [cx + x * scale, cy - y * scale];
  }

  class CanvasFX {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.particles = [];
      this.sparks = [];
      this.fireworks = [];
      this.trail = [];
      this.t = 0;
      this.running = false;
      this._onResize = () => this.resize();
      window.addEventListener("resize", this._onResize);
      this.resize();
    }

    resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.w = window.innerWidth;
      this.h = window.innerHeight;
      this.canvas.width = this.w * dpr;
      this.canvas.height = this.h * dpr;
      this.canvas.style.width = this.w + "px";
      this.canvas.style.height = this.h + "px";
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this.particles.length < 50) {
        for (let i = this.particles.length; i < 55; i++) {
          this.particles.push(new Particle(this.w, this.h));
        }
      }
    }

    start() {
      if (this.running) return;
      this.running = true;
      this.loop();
    }

    stop() {
      this.running = false;
    }

    burst(x, y) {
      this.fireworks.push(new Firework(x, this.h, y));
      for (let i = 0; i < 18; i++) {
        this.sparks.push(new Spark(x, y));
      }
    }

    celebrate() {
      const cx = this.w / 2;
      const cy = this.h / 2;
      for (let i = 0; i < 7; i++) {
        setTimeout(() => {
          this.burst(cx + rand(-140, 140), cy + rand(-100, 100));
        }, i * 180);
      }
    }

    loop() {
      if (!this.running) return;
      this.t++;
      const { ctx, w, h } = this;

      ctx.clearRect(0, 0, w, h);

      // 心形轨迹
      const cx = w / 2;
      const cy = h * 0.42;
      const scale = Math.min(w, h) * 0.011;
      const ht = this.t * 0.04;
      const [tx, ty] = heartPoint(ht, scale, cx, cy);
      this.trail.push({ x: tx, y: ty, hue: (this.t * 2) % 360 });
      if (this.trail.length > 100) this.trail.shift();

      for (const p of this.trail) {
        ctx.save();
        ctx.globalAlpha = 0.5;
        ctx.fillStyle = hsl(p.hue, 85, 65);
        drawHeart(ctx, p.x, p.y, 4);
        ctx.restore();
      }

      for (const p of this.particles) {
        p.update(w, h, this.t);
        p.draw(ctx);
      }

      this.fireworks = this.fireworks.filter((fw) => {
        fw.update(this.sparks);
        fw.draw(ctx);
        return !fw.exploded;
      });
      if (this.fireworks.length > 6) this.fireworks.shift();

      this.sparks = this.sparks.filter((s) => {
        s.update();
        if (s.life > 0) s.draw(ctx);
        return s.life > 0;
      });
      if (this.sparks.length > 400) this.sparks.splice(0, this.sparks.length - 400);

      requestAnimationFrame(() => this.loop());
    }
  }

  global.CanvasFX = CanvasFX;
})(window);
