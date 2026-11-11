# Figures: explanatory, memorable, academically appropriate

## Design first

For each figure, state the reader's question, one main takeaway, connection to the argument, evidence source, intended column width, and main/appendix placement. Favor a useful running example, a mechanism comparison, a revealing diagnostic, or an annotated real case over a generic stack of boxes. A visual can be distinctive without decorative clutter. Do not introduce unapproved terminology in labels.

Prefer TikZ/PGF for conceptual diagrams and PGFPlots for compatible quantitative plots. Use Matplotlib or other reproducible tools when data volume, heatmaps, or specialist visualizations justify them; use editable vector tooling for complex illustrations. Preserve editable sources, rendering commands, data transformations, and reproducibility. Do not force every image into TikZ. Do not require shell escape or install packages without consent. Use official package documentation referenced in `references/sources.md`.

Use a coherent, purposeful color palette; reuse semantic colors throughout. Make primary information visually prominent, but never use color alone to encode meaning. Use labels, markers, line styles, and adequate contrast. Test grayscale and color-vision accessibility where relevant. Keep readable type at actual publication scale; simplify or split overloaded figures instead of shrinking labels. Minimize accidental line crossings; intentionally crossing curves are valid data, not a layout defect. Route diagram connectors around labels and clearly show junctions.

Empirical figures must use traceable measured data. Do not invent or smooth away results, cherry-pick ranges, suppress uncertainty, or use misleading axes to 'sell' the work. Mark conceptual illustrations and synthetic examples clearly in the final caption when appropriate. Obtain approval for any new scientific claim or negative interpretation in a caption.

## Independent visual review

Use `prompts/visual-reviewer.md` in a separate context from the figure designer. Supply actual rendered figure images, the containing manuscript page at final scale, caption, intended takeaway, and data mapping when appropriate. A text-only model must mark visual review unavailable, never passed.

Perform two checks:
1. **Technical readability and integrity:** text/line collisions, clipped elements, occlusion, ambiguous arrows, crowded spacing, small type, missing legend/units, axis distortion, inconsistent symbols, data-caption mismatch, grayscale and contrast.
2. **Explanatory value and visual interest:** immediate focal point, meaningful hierarchy, clear reading order, useful example, connection to the argument, distinctive but disciplined visual idea. A tidy generic figure can still fail this check.

For each issue give figure/page/panel and location, evidence, severity, exact suggested repair, and what to recheck. Separate observed defects from subjective suggestions. Avoid changing the scientific meaning under the guise of design. After repair, re-render and inspect both figure and page. A resize or layout change invalidates previous visual approval for the affected render. Store render/PDF hashes with review results. Different independent reviewers may be used, but do not claim statistical independence.

## Every-page inspection

Follow `references/page-qa.md` for the final manuscript. Inspect every page separately as an image, including pages without figures, references, and appendices. A figure crop alone does not show surrounding layout. The current PDF must have complete individual-page observations before release.
