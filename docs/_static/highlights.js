(() => {
  const deck = document.querySelector(".manual-highlights");
  if (!deck) return;
  const slides = Array.from(deck.querySelectorAll(".product-hero"));
  // Local previews can open the image inline even when the link requests a download.
  for (const link of deck.querySelectorAll("a[download]")) {
    link.target = "_blank";
    link.relList.add("noopener");
    if (location.protocol === "file:") link.removeAttribute("download");
  }
  if (slides.length < 2) return;

  const labelText = Array.from(document.querySelectorAll(".demo-labels li"), item => item.textContent.trim());
  if (labelText.length !== 11) return;
  const [close, stepThrough, previousLabel, nextLabel, synchronizedViews, pickSet,
    pickHint, selectedTogether, highlights, resume, pause] = labelText;
  const dialog = document.createElement("dialog");
  dialog.className = "highlight-demo";
  document.body.append(dialog);

  function action(text, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.onclick = onClick;
    return button;
  }
  function addDemo(slide, title, render) {
    if (!dialog.showModal) return;
    const trigger = action(title, () => {
      clearTimeout(timer);
      const heading = document.createElement("h2");
      heading.id = "demo-heading";
      heading.textContent = title;
      dialog.setAttribute("aria-labelledby", heading.id);
      dialog.replaceChildren(heading);
      render();
      dialog.append(action(close, () => dialog.close()));
      dialog.showModal();
    });
    slide.querySelector(".manual-intro p:last-child").append(trigger);
  }
  addDemo(slides[0], stepThrough, () => {
    const image = document.createElement("img");
    const position = document.createElement("output");
    let step = 1;
    const prev = action(previousLabel, () => update(step - 1));
    const next = action(nextLabel, () => update(step + 1));
    function update(n) {
      step = n;
      image.src = "_static/playback/step-" + n + ".webp";
      image.alt = synchronizedViews;
      position.textContent = n + " / 5";
      prev.disabled = n === 1;
      next.disabled = n === 5;
    }
    update(1);
    dialog.append(image, prev, position, next);
  });
  addDemo(slides[2], pickSet, () => {
    const hint = document.createElement("p");
    hint.textContent = pickHint;
    const result = document.createElement("output");
    dialog.append(hint);
    const buttons = [];
    for (const source of ["A", "B"]) {
      const row = document.createElement("div");
      for (const name of ["01.png", "02.png", "03.png"]) {
        const button = action(source + "/" + name, () => {
          for (const item of buttons) item.setAttribute("aria-pressed", String(item.dataset.name === name));
          result.textContent = selectedTogether + " A/" + name + " + B/" + name;
        });
        button.dataset.name = name;
        button.setAttribute("aria-pressed", "false");
        buttons.push(button);
        row.append(button);
      }
      dialog.append(row);
    }
    dialog.append(result);
  });
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const controls = document.createElement("div");
  controls.className = "highlight-controls";
  controls.setAttribute("role", "group");
  controls.setAttribute("aria-label", highlights);
  const toggle = document.createElement("button");
  const selectors = slides.map((slide, i) => {
    const button = document.createElement("button");
    button.className = "highlight-selector";
    button.title = slide.querySelector(".manual-intro strong").textContent;
    button.setAttribute("aria-label", button.title);
    button.onclick = () => show(i);
    controls.append(button);
    return button;
  });
  controls.append(toggle);
  deck.append(controls);
  let index = 0;
  let paused = motion.matches;
  let timer;
  function schedule() {
    clearTimeout(timer);
    if (!paused && !dialog.open && !document.hidden && !deck.matches(":hover, :focus-within")) {
      timer = setTimeout(() => show(index + 1), 8000);
    }
  }
  function show(position) {
    index = (position + slides.length) % slides.length;
    slides.forEach((slide, i) => { slide.hidden = i !== index; });
    selectors.forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
    toggle.textContent = paused ? resume : pause;
    schedule();
  }
  toggle.onclick = () => { paused = !paused; show(index); };
  for (const event of ["mouseenter", "mouseleave", "focusin"]) deck.addEventListener(event, schedule);
  deck.addEventListener("focusout", () => setTimeout(schedule, 0));
  document.addEventListener("visibilitychange", schedule);
  dialog.addEventListener("close", schedule);
  motion.addEventListener("change", () => { paused = motion.matches; show(index); });
  show(0);
})();
