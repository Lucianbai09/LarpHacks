// Forms with a data-confirm message ask in Cove's own box before submitting.
document.addEventListener("submit", (event) => {
  const form = event.target;
  const message = form.dataset.confirm;
  const box = document.getElementById("confirm");
  if (!message || !box) return;
  event.preventDefault();
  box.querySelector(".confirm-message").textContent = message;
  box.returnValue = "";
  box.addEventListener("close", () => box.returnValue === "ok" && form.submit(), { once: true });
  box.showModal();
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

// Where a post goes: any number of communities, or Overall on its own.
document.addEventListener("change", (event) => {
  const box = event.target;
  if (box.name !== "category") return;
  const boxes = [...box.form.querySelectorAll('input[name="category"]')];
  const overall = boxes.find((each) => each.value === "");
  const communities = boxes.filter((each) => each !== overall);
  if (box === overall) {
    communities.forEach((each) => (each.checked = false));
    overall.checked = true;
  } else {
    overall.checked = !communities.some((each) => each.checked);
  }
});

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 3200);
}

// "I believe you" updates straight away and saves in the background, so the page never moves.
// Every copy of the post on the page changes together, and the server's answer has the last word.
function showBelief(action, believed, count) {
  for (const button of document.querySelectorAll(".action-btn[aria-pressed]")) {
    if (button.form.action !== action) continue;
    button.setAttribute("aria-pressed", believed);
    button.lastChild.textContent = `${believed ? "You believe this" : "I believe you"} (${count})`;
  }
}

document.addEventListener("submit", async (event) => {
  const form = event.target;
  const button = form.querySelector(".action-btn[aria-pressed]");
  if (!button) return;
  event.preventDefault();
  if (form.dataset.sending) return;
  form.dataset.sending = "true";

  const believed = button.getAttribute("aria-pressed") !== "true";
  const count = Number(button.textContent.match(/\((\d+)\)/)[1]);
  showBelief(form.action, believed, count + (believed ? 1 : -1));
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "fetch" },
    });
    const reply = await response.json();
    showBelief(form.action, reply.believed, reply.believers);
    if (reply.badges.length) showToast(`New badge: ${reply.badges.join(", ")}`);
    delete form.dataset.sending;
  } catch {
    // Logged out, rate limited or offline. A normal submit shows what went wrong.
    form.submit();
  }
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
  bag: ["...XXXXX...", "..X.....X..", "..X.....X..", "XXXXXXXXXXX", "X.........X", "X..X...X..X", "X.........X", "X.........X", "X.........X", "X.........X", "XXXXXXXXXXX"],
  cigarette: ["............X.", "...........X..", "............X.", "...........X..", "XXXXXXXXXXXXXX", "X......X...XXX", "X......X...XXX", "XXXXXXXXXXXXXX"],
  gamepad: [".XXXXXXXXXXXX.", "X............X", "X..X......X..X", "X.XXX....X.X.X", "X..X......X..X", "X....XXXX....X", "X...X....X...X", ".XXX......XXX."],
  dice: [".XXXXXXXXXX.", "X..........X", "X.XX....XX.X", "X.XX....XX.X", "X..........X", "X....XX....X", "X....XX....X", "X..........X", "X.XX....XX.X", "X.XX....XX.X", "X..........X", ".XXXXXXXXXX."],
  can: [".XXXXXX.", "XXXXXXXX", "X......X", "X....X.X", "X...XX.X", "X..XX..X", "X.XXXX.X", "X..XX..X", "X.XX...X", "X.X....X", "XXXXXXXX", ".XXXXXX."],
};

// x/y place each icon around the headline on wide screens, xs/ys in a band above it on phones.
const FLOATERS = [
  { ic: "phone", x: "11%", y: "6%", xs: "9%", ys: "22%", dx: "10px", dy: "-14px", dur: "6.4s", delay: "-1.2s", depth: 1.1 },
  { ic: "vape", x: "3.5%", y: "30%", dx: "-12px", dy: "10px", dur: "7.6s", delay: "-3.4s", depth: 0.7, alt: true, wideOnly: true },
  { ic: "beer", x: "12%", y: "56%", xs: "30%", ys: "50%", dx: "12px", dy: "8px", dur: "8.2s", delay: "-2.1s", depth: 1.3, alt: true },
  { ic: "cigarette", x: "5%", y: "82%", xs: "52%", ys: "14%", dx: "-8px", dy: "-12px", dur: "6.9s", delay: "-4.6s", depth: 0.9 },
  { ic: "gamepad", x: "88%", y: "7%", xs: "72%", ys: "52%", dx: "-10px", dy: "12px", dur: "7.2s", delay: "-0.6s", depth: 1.2, alt: true },
  { ic: "dice", x: "96%", y: "31%", xs: "89%", ys: "10%", dx: "8px", dy: "-10px", dur: "6.1s", delay: "-2.8s", depth: 0.6 },
  { ic: "can", x: "87%", y: "57%", dx: "12px", dy: "10px", dur: "8.6s", delay: "-5.2s", depth: 1.4, alt: true, wideOnly: true },
  { ic: "bag", x: "95%", y: "82%", dx: "-10px", dy: "-8px", dur: "7.4s", delay: "-1.8s", depth: 0.8, wideOnly: true },
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

// Icons lean away from the pointer, pause off screen and bounce when tapped.
function animateHero(hero) {
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
  new IntersectionObserver((entries) => hero.classList.toggle("paused", !entries[0].isIntersecting)).observe(hero);
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

// Shared posts rise out of the campfire like smoke, alternating sides on wide screens.
// They keep drifting under the pointer, and only stop while off screen or in a hidden tab.
function lightCampfire(stage) {
  const smoke = stage.querySelector("[data-campfire]");
  const posts = [...smoke.querySelectorAll(".ember-msg")];
  if (!posts.length || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  posts.forEach((post) => post.remove());
  stage.classList.add("lit", "paused");
  let next = 0;
  let lane = 0;
  let timer = null;
  let onScreen = false;
  const isWide = () => stage.clientWidth > 720;
  const every = () => (isWide() ? 3.4 : 5.8);
  const jitter = (range) => Math.round((Math.random() - 0.5) * range);
  const spawn = (delay = 0) => {
    const post = posts[next++ % posts.length].cloneNode(true);
    const side = lane++ % 2 ? 1 : -1;
    const offset = isWide() ? side * Math.min(250, stage.clientWidth * 0.23) : 0;
    const values = {
      delay: `${delay}s`, x0: `${Math.round(offset * 0.3)}px`, x1: `${Math.round(offset * 0.95) + jitter(16)}px`,
      xm: `${Math.round(offset) + jitter(30)}px`, x2: `${Math.round(offset * 1.1) + jitter(50)}px`,
      r0: `${-side * 2}deg`, r1: `${side * 3 + jitter(3)}deg`, rm: `${-side * 2 + jitter(4)}deg`, r2: `${side * 6 + jitter(4)}deg`,
    };
    // Set from here because the security policy blocks style="" attributes.
    for (const [name, value] of Object.entries(values)) post.style.setProperty(`--${name}`, value);
    post.addEventListener("animationend", () => post.remove());
    smoke.append(post);
    post.style.setProperty("--rise", `${Math.max(120, smoke.clientHeight - post.offsetHeight)}px`);
  };
  const tick = () => {
    spawn();
    timer = setTimeout(tick, every() * 1000);
  };
  const sync = () => {
    const running = onScreen && document.visibilityState === "visible";
    stage.classList.toggle("paused", !running);
    if (running && !timer) timer = setTimeout(tick, every() * 1000);
    if (!running && timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
  [0, 1, 2].forEach((k) => spawn(-k * every()));
  document.addEventListener("visibilitychange", sync);
  new IntersectionObserver((entries) => {
    onScreen = entries[0].isIntersecting;
    sync();
  }).observe(stage);
}

const floatField = document.querySelector(".float-field");
if (floatField) {
  drawFloaters(floatField);
  animateHero(document.querySelector(".land-hero"));
}
const campfire = document.querySelector(".fire-stage");
if (campfire) lightCampfire(campfire);
