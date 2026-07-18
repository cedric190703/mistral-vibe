const slides = [...document.querySelectorAll(".slide")];
const currentCount = document.querySelector(".controls__count span");
const progress = document.querySelector(".progress__fill");
const previousButton = document.querySelector('[data-action="previous"]');
const nextButton = document.querySelector('[data-action="next"]');
const fullscreenButton = document.querySelector('[data-action="fullscreen"]');
const notesPanel = document.querySelector(".presenter-notes");
const notesCopy = notesPanel.querySelector("p");

const notes = [
  "Arthuro devait présenter une future fonctionnalité de conversation à un client. Il a choisi de ne pas seulement la décrire : avec Vibe, il a créé un site inspiré d’un jeu de combat de créatures. La conversation devient une expérience gamifiée, donc plus facile à comprendre et à mémoriser pour différents publics.",
  "Le premier résultat, produit en un prompt, fonctionne très bien pour matérialiser l’idée. Mais il ne suffit pas pour une démonstration client. Une interface peut être globalement juste et conserver des défauts que seul un utilisateur voit : des chevauchements, des boutons mal placés ou un ordre d’interaction peu naturel.",
  "Notre principal ajout est vibe-in-chrome. Après l’installation du skill ou la mise à jour de la CLI forkée, Vibe peut contrôler Chrome pour ouvrir le site, suivre le parcours, constater les problèmes et vérifier les corrections. Cela ferme la boucle entre génération et validation dans le navigateur réel. La version est destinée à une contribution open source, avec une pull request à venir.",
  "Deux autres contributions rendent ce workflow plus pratique. local-ai-discovery aide à découvrir et sélectionner rapidement les modèles disponibles en local, ce qui améliore l’expérience pour les usages open source. Et les commandes /skills et /context permettent de comprendre immédiatement les capacités installées et le contexte actif. Ensemble, ces ajouts rendent la CLI plus observable et plus facile à piloter.",
  "Le résultat n’est pas seulement un meilleur site de démonstration. C’est une évolution du vibe coding : on passe d’un résultat impressionnant mais partiellement opaque à une boucle que l’on peut tester, comprendre et ajuster. Ce travail est porté par Matthieu Carré, Jacques Dumora et Cédric Brzyski. La prochaine étape est de finaliser la contribution OSS et la pull request.",
];

let current = 0;

function showSlide(index) {
  current = Math.max(0, Math.min(index, slides.length - 1));

  slides.forEach((slide, slideIndex) => {
    slide.classList.toggle("is-active", slideIndex === current);
    slide.classList.toggle("is-before", slideIndex < current);
    slide.setAttribute("aria-hidden", String(slideIndex !== current));
  });

  currentCount.textContent = String(current + 1).padStart(2, "0");
  progress.style.width = `${((current + 1) / slides.length) * 100}%`;
  previousButton.disabled = current === 0;
  nextButton.disabled = current === slides.length - 1;
  notesCopy.textContent = notes[current];
  document.title = `${slides[current].dataset.title} — Vibe`;
  window.location.hash = `slide-${current + 1}`;
}

function toggleNotes() {
  const isVisible = notesPanel.classList.toggle("is-visible");
  notesPanel.setAttribute("aria-hidden", String(!isVisible));
}

async function toggleFullscreen() {
  if (document.fullscreenElement) {
    await document.exitFullscreen();
    return;
  }
  await document.documentElement.requestFullscreen();
}

previousButton.addEventListener("click", () => showSlide(current - 1));
nextButton.addEventListener("click", () => showSlide(current + 1));
fullscreenButton.addEventListener("click", toggleFullscreen);

document.addEventListener("keydown", (event) => {
  if (["ArrowRight", "PageDown", " "].includes(event.key)) {
    event.preventDefault();
    showSlide(current + 1);
  }
  if (["ArrowLeft", "PageUp"].includes(event.key)) {
    event.preventDefault();
    showSlide(current - 1);
  }
  if (event.key === "Home") showSlide(0);
  if (event.key === "End") showSlide(slides.length - 1);
  if (event.key.toLowerCase() === "f") toggleFullscreen();
  if (event.key.toLowerCase() === "n") toggleNotes();
});

let touchStart = null;

document.addEventListener("touchstart", (event) => {
  touchStart = event.changedTouches[0].clientX;
});

document.addEventListener("touchend", (event) => {
  if (touchStart === null) return;
  const distance = event.changedTouches[0].clientX - touchStart;
  if (Math.abs(distance) > 60) showSlide(current + (distance < 0 ? 1 : -1));
  touchStart = null;
});

const initialSlide = Number.parseInt(window.location.hash.replace("#slide-", ""), 10);
showSlide(Number.isNaN(initialSlide) ? 0 : initialSlide - 1);
