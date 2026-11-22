# Topic scope: stellar magnitudes and distance

Teach Bot teaches only what is in this document, plus standard physics. Every
formula here was checked against `tools/physics.py`, which the data filter and
the evaluation also use. The tutor gets this document pinned into every turn
(its "persistent memory" of the source material), so it never has to recall
a textbook detail from its weights.

Conventions used throughout: distances in parsecs (pc) unless stated,
log means log base 10, and **brighter means a smaller magnitude**.

## S1 Inverse-square law and flux

- A star of luminosity L sends its light out evenly over a sphere. At distance d
  that sphere has area 4πd², so the flux (light per unit area) is
  **F = L / (4πd²)**.
- k times farther away gives 1/k² of the flux. Ten times farther: one hundredth.
- Everyday picture: a spray-paint can. Twice as far from the wall, the paint
  covers four times the area, so each patch is a quarter as thick.
- Common mistakes: thinking 10× farther is 10× fainter (forgetting the square);
  confusing luminosity (what the star emits, watts) with flux (what reaches you, W/m²).

## S2 The magnitude scale

- Apparent magnitude m measures how bright a star looks from Earth.
- The scale runs backwards: smaller numbers are brighter. Vega is about 0,
  Sirius is about −1.46, the faintest naked-eye stars are about +6.
- A factor of 100 in flux is exactly 5 magnitudes (Pogson's definition), so one
  magnitude is a factor of 100^(1/5) ≈ 2.512.
- Common mistakes: thinking a larger magnitude means brighter; thinking the
  scale is linear (that a 2nd-magnitude star is half as bright as a 1st).

## S3 Magnitude differences and flux ratios

- **m₂ − m₁ = −2.5 log(F₂ / F₁)**, equivalently **F₂ / F₁ = 10^(−0.4 (m₂ − m₁))**.
- Several unresolved stars: add their fluxes, then convert back. Never add
  magnitudes. Two identical stars together are 2.5 log 2 ≈ 0.75 mag brighter.
- Common mistakes: adding magnitudes directly; dropping the minus sign.

## S4 Absolute magnitude and the distance modulus

- Absolute magnitude M is the apparent magnitude the star would have at 10 pc.
  It measures luminosity on the magnitude scale.
- **m − M = 5 log(d / 10 pc)**, so **d = 10^((m − M)/5 + 1) pc**.
- m − M is called the distance modulus μ. It is 0 at 10 pc, +5 at 100 pc, +10 at 1 kpc.
- Common mistakes: writing 5 log d without the 10 pc; using light-years in the formula.

## S5 Parallax and distance units

- **d [pc] = 1 / p [arcsec]**. A parallax of 0.1″ means 10 pc.
- 1 pc ≈ 3.26 light-years ≈ 206 265 AU ≈ 3.086 × 10¹⁶ m.
- Common mistakes: using parallax in milliarcseconds without converting;
  mixing light-years into the distance modulus.

## S6 Extinction and luminosity

- Dust dims starlight by A magnitudes: **m − M = 5 log(d / 10 pc) + A**.
  Ignoring extinction makes a star seem farther than it is.
- Luminosity ratio from absolute magnitudes: **L₁ / L₂ = 10^(−0.4 (M₁ − M₂))**.
  The Sun's absolute bolometric magnitude is 4.74.
- Common mistakes: subtracting A on the wrong side; applying A when the
  problem says to ignore interstellar absorption.
