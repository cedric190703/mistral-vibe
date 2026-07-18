const path = require("node:path");
const pptxgen = require("pptxgenjs");

const CREAM = "F3EEE1";
const BLACK = "141414";
const ORANGE = "FF6A13";
const ORANGE_DEEP = "FA500F";
const RED = "E10500";
const YELLOW = "FFD800";
const WHITE = "FFFFFF";
const MUTED = "6B6558";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Matthieu Carré, Jacques Dumora, Cédric Brzyski";
pres.subject = "Vibe — observable development loop";
pres.title = "Vibe: From one shot to an observable development loop";
pres.company = "Mistral AI";
pres.lang = "en-US";

function bgRect(slide, color) {
  slide.background = { color };
}

function pixelCluster(slide, x, y, scale, colors) {
  const size = 0.16 * scale;
  const cells = [
    [0, 0],
    [1, 0],
    [0, 1],
    [2, 1],
    [1, 2],
    [2, 0],
  ];
  cells.forEach(([cellX, cellY], index) => {
    slide.addShape("rect", {
      x: x + cellX * size,
      y: y + cellY * size,
      w: size * 0.9,
      h: size * 0.9,
      fill: { color: colors[index % colors.length] },
      line: { type: "none" },
    });
  });
}

function blockIcon(slide, x, y, dimension, fillColor) {
  slide.addShape("rect", {
    x,
    y,
    w: dimension,
    h: dimension,
    fill: { color: fillColor },
    line: { type: "none" },
  });
}

function kicker(slide, label, color, textColor = BLACK) {
  blockIcon(slide, 0.7, 0.55, 0.22, color);
  const [number] = label.split(" ");
  slide.addText(number, {
    x: 1.05,
    y: 0.48,
    w: 3.5,
    h: 0.4,
    fontFace: "Arial",
    fontSize: 14,
    color: textColor,
    bold: true,
    margin: 0,
  });
}

{
  const slide = pres.addSlide();
  bgRect(slide, BLACK);
  pixelCluster(slide, 10.35, 0.6, 6, [
    ORANGE,
    RED,
    YELLOW,
    ORANGE_DEEP,
    ORANGE,
    YELLOW,
  ]);
  slide.addText("VIBE", {
    x: 0.7,
    y: 0.9,
    w: 8,
    h: 0.6,
    fontFace: "Arial",
    fontSize: 16,
    color: ORANGE,
    bold: true,
    charSpacing: 5,
    margin: 0,
  });
  slide.addText("From “one shot” to an\nobservable development loop", {
    x: 0.7,
    y: 1.55,
    w: 10.8,
    h: 2.4,
    fontFace: "Arial",
    fontSize: 50,
    color: WHITE,
    bold: true,
    lineSpacingMultiple: 1.1,
    margin: 0,
  });
  slide.addShape("rect", {
    x: 0.72,
    y: 3.85,
    w: 0.5,
    h: 0.08,
    fill: { color: ORANGE },
    line: { type: "none" },
  });
  slide.addText(
    "Turning a client demo into a development workflow you can actually test in Chrome",
    {
      x: 0.7,
      y: 4.05,
      w: 9.7,
      h: 0.8,
      fontFace: "Arial",
      fontSize: 18,
      color: CREAM,
      margin: 0,
    },
  );
  slide.addText("Matthieu Carré   ·   Jacques Dumora   ·   Cédric Brzyski", {
    x: 0.7,
    y: 6.55,
    w: 10,
    h: 0.5,
    fontFace: "Arial",
    fontSize: 14,
    color: ORANGE,
    bold: true,
    margin: 0,
  });
}

function featureSlide(number, badgeColor, codeName, tagline, points, note) {
  const slide = pres.addSlide();
  bgRect(slide, CREAM);
  kicker(slide, number, badgeColor);

  slide.addShape("rect", {
    x: 0.7,
    y: 1.55,
    w: 0.85,
    h: 0.85,
    fill: { color: badgeColor },
    line: { type: "none" },
  });
  slide.addText(codeName, {
    x: 1.75,
    y: 1.55,
    w: 9.5,
    h: 0.6,
    fontFace: "Courier New",
    fontSize: 35,
    bold: true,
    color: BLACK,
    valign: "middle",
    margin: 0,
  });
  slide.addText(tagline, {
    x: 1.75,
    y: 2.15,
    w: 9.8,
    h: 0.6,
    fontFace: "Arial",
    fontSize: 18,
    italic: true,
    color: MUTED,
    margin: 0,
  });

  slide.addShape("rect", {
    x: 0.7,
    y: 3,
    w: 11.9,
    h: 3.65,
    fill: { color: WHITE },
    line: { color: BLACK, width: 1 },
  });
  slide.addShape("rect", {
    x: 0.7,
    y: 3,
    w: 11.9,
    h: 0.08,
    fill: { color: badgeColor },
    line: { type: "none" },
  });

  const numberedPoints = points
    .map((point, index) => `${String(index + 1).padStart(2, "0")}   ${point}`)
    .join("\n");
  slide.addText(numberedPoints, {
    x: 1.05,
    y: 3.55,
    w: 11.1,
    h: 2.5,
    fontFace: "Arial",
    fontSize: 17,
    color: BLACK,
    breakLine: false,
    lineSpacingMultiple: 1.25,
    paraSpaceAfter: 10,
    margin: 0,
  });

  if (note) {
    slide.addText(note, {
      x: 0.7,
      y: 6.85,
      w: 11.9,
      h: 0.45,
      fontFace: "Arial",
      fontSize: 12,
      italic: true,
      color: MUTED,
      align: "center",
      margin: 0,
    });
  }
}

featureSlide(
  "01 / FEATURE",
  ORANGE,
  "vibe-in-chrome",
  "Vibe drives a real Chrome browser to test the interface it just generated",
  [
    "Opens the generated site and walks through the actual user journey — not just the code",
    "Surfaces UI bugs a one-shot prompt can't catch: overlaps, misplaced buttons, confusing interaction order",
    "Closes the loop: open → try → observe → fix → verify again",
    "Ships as an installable OSS skill, built on a forked CLI",
  ],
  "OSS contribution and pull request in progress",
);

featureSlide(
  "02 / FEATURE",
  RED,
  "local-ai-discovery",
  "Find and select locally available models in seconds",
  [
    "Scans what's actually running locally, no manual lookup needed",
    "Lets you switch models on the fly to match the task at hand",
    "Smooths out open-source workflows that depend on local inference",
    "Removes a common point of friction when experimenting with new models",
  ],
  null,
);

featureSlide(
  "03 / FEATURE",
  YELLOW,
  "/skills  ·  /local",
  "Commands that make the session's capabilities visible at a glance",
  [
    "/skills lists what's installed, active, and actually available in the current session",
    "/local was added by Cédric — visible in his latest pull request on GitHub",
    "Turns a black-box CLI into something you can inspect before you rely on it",
    "Reduces guesswork when debugging why a capability isn't behaving as expected",
  ],
  null,
);

{
  const slide = pres.addSlide();
  bgRect(slide, CREAM);
  kicker(slide, "04 / USE CASES", ORANGE);
  slide.addText("Where this workflow pays off", {
    x: 0.7,
    y: 1,
    w: 11.5,
    h: 0.8,
    fontFace: "Arial",
    fontSize: 35,
    color: BLACK,
    bold: true,
    margin: 0,
  });

  const cases = [
    {
      title: "Client-facing demos",
      desc: "Turn a one-shot AI generation into something you can confidently present live — no last-minute surprises.",
    },
    {
      title: "UI / UX debugging",
      desc: "Catch overlaps, misplaced buttons, and confusing flows before they reach a real user.",
    },
    {
      title: "Open-source & local workflows",
      desc: "Pick the right local model fast, without breaking flow to go looking for it.",
    },
    {
      title: "Session onboarding",
      desc: "Know exactly what's installed and active before you start debugging or demoing.",
    },
  ];

  const cardWidth = 5.75;
  const cardHeight = 2.1;
  const gapX = 0.4;
  const gapY = 0.35;
  const startX = 0.7;
  const startY = 2.05;
  cases.forEach((item, index) => {
    const column = index % 2;
    const row = Math.floor(index / 2);
    const x = startX + column * (cardWidth + gapX);
    const y = startY + row * (cardHeight + gapY);
    slide.addShape("rect", {
      x,
      y,
      w: cardWidth,
      h: cardHeight,
      fill: { color: WHITE },
      line: { color: BLACK, width: 1 },
    });
    slide.addShape("rect", {
      x,
      y,
      w: 0.35,
      h: cardHeight,
      fill: { color: [ORANGE, RED, YELLOW, ORANGE_DEEP][index] },
      line: { type: "none" },
    });
    slide.addText(item.title, {
      x: x + 0.55,
      y: y + 0.25,
      w: cardWidth - 0.8,
      h: 0.5,
      fontFace: "Arial",
      fontSize: 24,
      bold: true,
      color: BLACK,
      margin: 0,
    });
    slide.addText(item.desc, {
      x: x + 0.55,
      y: y + 0.85,
      w: cardWidth - 0.8,
      h: 1.1,
      fontFace: "Arial",
      fontSize: 16,
      color: MUTED,
      lineSpacingMultiple: 1.3,
      margin: 0,
    });
  });
}

{
  const slide = pres.addSlide();
  bgRect(slide, BLACK);
  kicker(slide, "05 / DEMO", ORANGE, ORANGE);
  slide.addText("See it in action", {
    x: 0.7,
    y: 1,
    w: 11,
    h: 0.8,
    fontFace: "Arial",
    fontSize: 36,
    color: WHITE,
    bold: true,
    margin: 0,
  });
  slide.addText("vibe-in-chrome driving the demo built for Arthuro", {
    x: 0.7,
    y: 1.75,
    w: 9,
    h: 0.5,
    fontFace: "Arial",
    fontSize: 18,
    italic: true,
    color: CREAM,
    margin: 0,
  });

  const videoX = 1.9;
  const videoY = 2.5;
  const videoWidth = 9.5;
  const videoHeight = 4.25;
  slide.addShape("rect", {
    x: videoX,
    y: videoY,
    w: videoWidth,
    h: videoHeight,
    fill: { color: "1E1A15" },
    line: { color: ORANGE, width: 1.5 },
  });
  const playDimension = 1;
  slide.addShape("rect", {
    x: videoX + videoWidth / 2 - playDimension / 2,
    y: videoY + videoHeight / 2 - playDimension / 2 - 0.25,
    w: playDimension,
    h: playDimension,
    fill: { color: ORANGE_DEEP },
    line: { type: "none" },
  });
  slide.addShape("triangle", {
    x: videoX + videoWidth / 2 - 0.16,
    y: videoY + videoHeight / 2 - 0.47,
    w: 0.34,
    h: 0.44,
    fill: { color: WHITE },
    line: { type: "none" },
    rotate: 90,
  });
  slide.addText("Insert the demo video here", {
    x: videoX,
    y: videoY + videoHeight / 2 + 0.35,
    w: videoWidth,
    h: 0.5,
    align: "center",
    fontFace: "Arial",
    fontSize: 18,
    bold: true,
    color: WHITE,
    margin: 0,
  });
  slide.addText("(right-click this frame → Insert → Video from File)", {
    x: videoX,
    y: videoY + videoHeight / 2 + 0.8,
    w: videoWidth,
    h: 0.4,
    align: "center",
    fontFace: "Arial",
    fontSize: 11,
    italic: true,
    color: CREAM,
    margin: 0,
  });
  slide.addText(
    "Before / after: from a one-prompt interface to a version tested and fixed through Chrome.",
    {
      x: 0.7,
      y: 6.95,
      w: 11.9,
      h: 0.4,
      fontFace: "Arial",
      fontSize: 12,
      color: CREAM,
      italic: true,
      align: "center",
      margin: 0,
    },
  );
}

{
  const slide = pres.addSlide();
  bgRect(slide, BLACK);
  pixelCluster(slide, 10.75, 0.7, 5, [ORANGE, RED, YELLOW]);
  slide.addText("Questions?", {
    x: 0.7,
    y: 2.5,
    w: 8.5,
    h: 1.6,
    fontFace: "Arial",
    fontSize: 54,
    color: WHITE,
    bold: true,
    margin: 0,
  });
  slide.addShape("rect", {
    x: 0.72,
    y: 3.55,
    w: 0.6,
    h: 0.09,
    fill: { color: ORANGE },
    line: { type: "none" },
  });
  slide.addText("Q & A", {
    x: 0.7,
    y: 3.75,
    w: 8,
    h: 0.6,
    fontFace: "Arial",
    fontSize: 20,
    color: ORANGE,
    bold: true,
    charSpacing: 3,
    margin: 0,
  });
  slide.addText(
    "Next step: finalize the open-source contribution and open the pull request.",
    {
      x: 0.7,
      y: 4.7,
      w: 9.5,
      h: 0.6,
      fontFace: "Arial",
      fontSize: 18,
      italic: true,
      color: CREAM,
      margin: 0,
    },
  );
  slide.addText("Matthieu Carré   ·   Jacques Dumora   ·   Cédric Brzyski", {
    x: 0.7,
    y: 6.7,
    w: 11,
    h: 0.5,
    fontFace: "Arial",
    fontSize: 14,
    bold: true,
    color: ORANGE,
    margin: 0,
  });
}

const outputPath = path.join(__dirname, "Vibe_Presentation_EN.pptx");
pres.writeFile({ fileName: outputPath }).then(() => {
  console.log(`Presentation written to ${outputPath}`);
});
