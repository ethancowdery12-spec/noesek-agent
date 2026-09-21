# UI Library Reference (adopted Sep 21, roadmap items 34-36)

Ethan's call: un-park the UI libraries as **knowledge** - no runtime dependency,
no vendored code. This doc is the collected usage patterns; the system prompt
carries the distilled version and points here.

All three libraries are MIT licensed. Snippets largely copied from their docs or
catalogs keep a credit comment; patterns re-expressed in our own code need none.

## anime.js v4 - `juliangarnier/anime` (MIT, 72k stars)

General-purpose JS animation engine: CSS properties, SVG, DOM attributes, JS objects.

```js
import { animate, stagger, createTimeline } from 'animejs';

animate('.card', { translateY: [-20, 0], opacity: [0, 1], duration: 600, ease: 'outExpo' });
animate('.item', { scale: [0.8, 1], delay: stagger(80), ease: 'outBack' });

const tl = createTimeline({ defaults: { duration: 400, ease: 'outQuad' } });
tl.add('.panel', { translateX: [100, 0] })
  .add('.title', { opacity: [0, 1] }, '-=200'); // position offset overlaps steps
```

When to use: choreographed sequences, staggering lists, SVG path motion, anything
beyond a one-state CSS transition.

## Motion (a.k.a. Framer Motion / motion.dev) - `motiondivision/motion` (MIT)

Two surfaces, same engine:

Vanilla JS:
```js
import { animate, spring, inView } from 'motion';

animate('.box', { rotate: 90 }, { easing: spring({ stiffness: 300, damping: 20 }) });
inView('.reveal', (el) => { animate(el, { opacity: [0, 1], y: [24, 0] }); });
```

React:
```jsx
import { motion } from 'motion/react';

<motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            whileHover={{ scale: 1.03 }} transition={{ type: 'spring', stiffness: 260 }} />
```

When to use: physics-feeling motion (springs), scroll-linked reveals, gestures
(hover/tap/drag), React apps.

## kokonutui - `kokonut-labs/kokonutui` (MIT, 2k stars)

Copy-paste Tailwind CSS + React component catalog (buttons, cards, inputs, loaders,
backgrounds). Pattern: pick the component, paste its JSX + classes, adapt copy and
colors to the host app, credit kokonutui in a comment when the snippet is largely
unchanged.

When to use: fast, decent-looking UI without designing from scratch - dashboards,
landing sections, forms.

## Choosing

- Trivial hover/fade: plain CSS transitions - no library.
- Choreographed/sequenced animation, SVG motion: anime.js.
- Springs, gestures, scroll reveals, React: Motion.
- Ready-made components: kokonutui (+ Motion for their micro-interactions).
