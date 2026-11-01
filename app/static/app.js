// Forms with a data-confirm message ask before submitting.
document.addEventListener("submit", (event) => {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

// The eye button in a password field shows what you typed.
document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-pass-toggle]");
  if (!toggle) return;
  const input = toggle.parentElement.querySelector("input");
  const showing = input.type === "text";
  input.type = showing ? "password" : "text";
  toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  toggle.setAttribute("aria-pressed", String(!showing));
  toggle.querySelector("use").setAttribute("href", showing ? "#i-eye" : "#i-eye-off");
});

// A photo picked on the Write page shows a preview, and can be removed before posting.
const photoInput = document.querySelector("[data-photo-input]");
if (photoInput) {
  const preview = document.querySelector("[data-photo-preview]");
  const image = preview.querySelector("img");
  const clearPhoto = () => {
    photoInput.value = "";
    preview.hidden = true;
    image.removeAttribute("src");
  };
  photoInput.addEventListener("change", () => {
    const file = photoInput.files[0];
    const maxMb = Number(photoInput.dataset.maxMb);
    if (file && file.size > maxMb * 1024 * 1024) {
      window.alert(`Photos can be up to ${maxMb} MB. Please pick a smaller one.`);
      clearPhoto();
    } else if (file) {
      image.src = URL.createObjectURL(file);
      preview.hidden = false;
    } else {
      clearPhoto();
    }
  });
  preview.querySelector("button").addEventListener("click", clearPhoto);
}

// ---- Landing page

// Pixel icons of the habits people quit, drawn on a grid (X = filled).
const PIXEL = {
  phone: ["XXXXXXXX", "X......X", "X.XXXX.X", "X.X..X.X", "X.X..X.X", "X.X..X.X", "X.X..X.X", "X.XXXX.X", "X......X", "X..XX..X", "X......X", "XXXXXXXX"],
  vape: [".XXX..XXX.", "X...XX...X", "X........X", ".XXXXXXXX.", "..........", "....XX....", "...XXXX...", "...X..X...", "...X..X...", "...XXXX...", "...X..X...", "...XXXX..."],
  beer: [".XX..XX....", "XXXXXXXXX..", "X.......XXX", "X.X.X.X.X.X", "X.X.X.X.X.X", "X.X.X.X.X.X", "X.......XXX", "X.......X..", "XXXXXXXXX.."],
  wine: ["XXXXXXXXX", "X.......X", "XXXXXXXXX", "XXXXXXXXX", ".XXXXXXX.", "..XXXXX..", "....X....", "....X....", "....X....", "..XXXXX.."],
  cigarette: ["............X.", "...........X..", "............X.", "...........X..", "XXXXXXXXXXXXXX", "X......X...XXX", "X......X...XXX", "XXXXXXXXXXXXXX"],
  gamepad: [".XXXXXXXXXXXX.", "X............X", "X..X......X..X", "X.XXX....X.X.X", "X..X......X..X", "X....XXXX....X", "X...X....X...X", ".XXX......XXX."],
  dice: [".XXXXXXXXXX.", "X..........X", "X.XX....XX.X", "X.XX....XX.X", "X..........X", "X....XX....X", "X....XX....X", "X..........X", "X.XX....XX.X", "X.XX....XX.X", "X..........X", ".XXXXXXXXXX."],
  coffee: [".X..X......", "X..X.......", ".X..X......", "...........", "XXXXXXXXX..", "X.......XXX", "X.......X.X", "X.......XXX", "X.......X..", ".X.....X...", "..XXXXX...."],
};

// x/y place each icon around the headline on wide screens, xs/ys in a band above it on phones.
const FLOATERS = [
  { ic: "phone", x: "11%", y: "6%", xs: "9%", ys: "22%", dx: "10px", dy: "-14px", dur: "6.4s", delay: "-1.2s", depth: 1.1 },
  { ic: "vape", x: "3.5%", y: "30%", dx: "-12px", dy: "10px", dur: "7.6s", delay: "-3.4s", depth: 0.7, alt: true, wideOnly: true },
  { ic: "beer", x: "12%", y: "56%", xs: "30%", ys: "50%", dx: "12px", dy: "8px", dur: "8.2s", delay: "-2.1s", depth: 1.3, alt: true },
  { ic: "cigarette", x: "5%", y: "82%", xs: "52%", ys: "14%", dx: "-8px", dy: "-12px", dur: "6.9s", delay: "-4.6s", depth: 0.9 },
  { ic: "gamepad", x: "88%", y: "7%", xs: "72%", ys: "52%", dx: "-10px", dy: "12px", dur: "7.2s", delay: "-0.6s", depth: 1.2, alt: true },
  { ic: "dice", x: "96%", y: "31%", xs: "89%", ys: "10%", dx: "8px", dy: "-10px", dur: "6.1s", delay: "-2.8s", depth: 0.6 },
  { ic: "coffee", x: "87%", y: "57%", dx: "12px", dy: "10px", dur: "8.6s", delay: "-5.2s", depth: 1.4, alt: true, wideOnly: true },
  { ic: "wine", x: "95%", y: "82%", dx: "-10px", dy: "-8px", dur: "7.4s", delay: "-1.8s", depth: 0.8, wideOnly: true },
];

function drawFloaters(field) {
  FLOATERS.forEach((floater, k) => {
    const rows = PIXEL[floater.ic];
    const cols = Math.max(...rows.map((row) => row.length));
    let rects = "";
    rows.forEach((row, y) => {
      for (const run of row.matchAll(/X+/g)) {
        rects += `<rect x="${run.index}" y="${y}" width="${run[0].length}" height="1"></rect>`;
      }
    });

    const wrap = document.createElement("span");
    wrap.className = `float-wrap${floater.alt ? " alt" : ""}${floater.wideOnly ? " wide-only" : ""}`;
    wrap.innerHTML = `<span class="float-ic"><span class="float-in"><svg class="pix" viewBox="0 0 ${cols} ${rows.length}" shape-rendering="crispEdges" aria-hidden="true">${rects}</svg></span></span>`;
    // Set from here because the security policy blocks style="" attributes.
    const values = { ...floater, xs: floater.xs || floater.x, ys: floater.ys || floater.y, k, cols };
    for (const name of ["x", "y", "xs", "ys", "dx", "dy", "dur", "delay", "depth", "k", "cols"]) {
      wrap.style.setProperty(`--${name}`, values[name]);
    }
    field.append(wrap);
  });
}

// Pointer parallax, scroll drift, and the window's tabs walking through the feature cards.
function animateLanding(hero, stage) {
  const motion = !matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (motion && matchMedia("(pointer: fine)").matches) {
    hero.addEventListener("pointermove", (event) => {
      const box = hero.getBoundingClientRect();
      hero.style.setProperty("--px", (((event.clientX - box.left) / box.width) * 2 - 1).toFixed(3));
      hero.style.setProperty("--py", (((event.clientY - box.top) / box.height) * 2 - 1).toFixed(3));
    });
    hero.addEventListener("pointerleave", () => {
      hero.style.setProperty("--px", 0);
      hero.style.setProperty("--py", 0);
    });
  }

  if (motion) {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const box = stage.getBoundingClientRect();
        const progress = Math.min(1, Math.max(0, (innerHeight - box.top) / (innerHeight + box.height)));
        stage.style.setProperty("--s", (progress - 0.5).toFixed(3));
      });
    };
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Loops pause while they're off screen.
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => entry.target.classList.toggle("paused", !entry.isIntersecting));
  });
  [hero, stage].forEach((element) => observer.observe(element));

  const tabs = [...stage.querySelectorAll(".win-tab")];
  const cards = [...stage.querySelectorAll(".fcard")];
  let active = 0;
  let timer = null;
  const setActive = (index) => {
    active = index;
    tabs.forEach((tab, n) => tab.setAttribute("aria-pressed", n === index));
    cards.forEach((card, n) => card.classList.toggle("is-active", n === index));
  };
  const start = () => {
    if (motion && !timer) timer = setInterval(() => setActive((active + 1) % cards.length), 2800);
  };
  const stop = () => {
    clearInterval(timer);
    timer = null;
  };
  start();
  stage.addEventListener("pointerenter", stop);
  stage.addEventListener("pointerleave", start);
  tabs.forEach((tab, n) => tab.addEventListener("click", () => setActive(n)));
  stage.querySelectorAll(".fcard-wrap").forEach((wrap, n) => wrap.addEventListener("pointerenter", () => setActive(n)));
  hero.querySelectorAll(".float-wrap").forEach((wrap) => {
    wrap.addEventListener("click", () => {
      if (!motion) return;
      const icon = wrap.querySelector(".float-in");
      icon.classList.remove("boop");
      void icon.offsetWidth;
      icon.classList.add("boop");
    });
  });
}

const floatField = document.querySelector(".float-field");
if (floatField) {
  drawFloaters(floatField);
  animateLanding(document.querySelector(".land-hero"), document.querySelector(".stage"));
}
