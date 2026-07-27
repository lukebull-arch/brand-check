# Framer agent prompt: GEEIQ brand check page

How to use this package:

1. In Framer, create a new page at `/brand-check`.
2. Add the code component first: Assets > Code > New file, name it `BrandCheckHero`, paste in the contents of `BrandCheckHero.tsx` (in this folder). It has property controls for the webhook URL, avatar image and report link.
3. Paste the prompt below into the Framer AI agent on that page.
4. Attach 2 or 3 screenshots of the built page (desktop and mobile) as visual reference. The agent follows images better than adjectives.
5. After the agent finishes, place the `BrandCheckHero` component at the top of the page (below the nav), upload the avatar PNG to its image property, and set the webhook URL property.

---

## Prompt (paste everything below this line)

Build a landing page at /brand-check called "GEEIQ brand check". It is a lead generation page for checking a brand's presence in virtual worlds. Use our existing site nav and footer. I will place a code component called BrandCheckHero at the top of the page myself, so leave a placeholder section for it and do not build the hero or any input form.

### Brand system, follow exactly

Colours:
- Primary purple #7C68FB (buttons, links, accents)
- Dark amethyst #2E204D (headings, stats band background)
- Warm off-white #FAF7F2 (page background)
- Coral red #FC4F3F (small accents only, never a background fill)
- White #FFFFFF (cards)
- Light purple tint #EEEDFE (skeleton shapes, soft card fills)

Typography:
- Headings: Plus Jakarta Sans, weight 600
- Body: Figtree, weight 400, 16px base
- Sentence case everywhere. No all caps, no title case.

Copy rules: UK English. No em dashes anywhere, use full stops or commas. No exclamation marks. Never use the words ecosystem, intelligence platform, seamless, leverage, or unlock. Use the copy below verbatim, do not paraphrase it.

### Page structure, in order

1. Placeholder section for the BrandCheckHero code component (about 700px tall, off-white background). Do not design anything inside it.

2. "Your brand may already be there" section. Max width about 760px, left aligned.
   Heading: "Your brand may already be there"
   Paragraph 1: "Virtual worlds are creator-led economies. Players build experiences, items and communities around the brands they love, with or without permission. That means your brand can have a footprint in Roblox or Fortnite long before you've ever run an activation."
   Paragraph 2: "Fan-made experiences. User-generated items. Unofficial tributes and knock-offs. This activity shapes how millions of players encounter your brand every day, and most brands have never seen it."
   Closing line, medium weight: "We track it. Enter your brand above and we'll show you what's out there."

3. Brand ticker. Reuse the exact logo ticker component from our homepage (the scrolling monochrome brand belt with faded edges). Label above it, small, centred, muted: "Brands already showing up in virtual worlds".

4. Stats band. Full width, dark amethyst #2E204D background, 4 stats in a row, stacking 2x2 on mobile. White numbers in Plus Jakarta Sans, light purple #C9C0E6 labels below each. The stats, keep the [X] placeholders literal:
   - "8 years" / "tracking virtual worlds"
   - "[X]" / "brands tracked"
   - "[X]" / "activations logged"
   - "[X]" / "platforms covered"

5. "What you'll get" section. Two columns on desktop, stacking on mobile.
   Left column:
   Heading: "What you'll get"
   Intro: "A short, bespoke report on your brand's footprint in virtual worlds, built by a GEEIQ analyst from our platform data. Inside:"
   Four bullets with small purple ring markers:
   - "Where your brand appears today, including official activity and creator-made content"
   - "A handful of stats specific to your brand, pulled fresh from 8 years of tracking"
   - "How your category is showing up across Roblox, Fortnite and other platforms"
   - "A short guide to how brands enter virtual worlds, and where most get it wrong"
   Below the bullets, a caption in coral #FC4F3F, semibold, 15px: "Built by a GEEIQ analyst, not a bot"
   Right column: a small skeleton mockup suggesting a report PDF. White card, rounded 16px, soft shadow. Inside: one purple bar (60% width), three light purple lines, a 2x2 pair of light stat blocks, two more light lines. All shapes in #EEEDFE on white.

6. "How it works" section. Centred heading "How it works", then 3 white cards in a row (stacking on mobile), each with a numbered circle (light purple background, purple number):
   1. "Tell us your brand." / "Takes ten seconds."
   2. "We pull the data." / "A GEEIQ analyst checks your brand's footprint across the platforms we track."
   3. "Your report lands in your inbox." / "Within 2 working days, free."

7. Footer CTA. Full width, dark amethyst background, centred.
   Heading in white: "See the full picture"
   Body in light purple #C9C0E6: "The report is a snapshot. The GEEIQ platform tracks brand activity across virtual worlds every day, for teams who need more than a one-off check."
   Purple button: "Book a demo" linking to the demo booking page.

### Page settings

Title: "Check your brand's presence in virtual worlds | GEEIQ"
Description: "Virtual worlds are creator-led. Your brand may already appear in Roblox and Fortnite through fan-made content. Get a free report on your brand's footprint, built by a GEEIQ analyst."
Set the Open Graph title and description to the same values.

### Layout rules

Content max width 1120px. Generous vertical rhythm, roughly 80px between sections on desktop, 56px on mobile. Test at 375px and 1440px, no horizontal scroll at either. Coral must stay a small accent, well under 10 percent of the page.
