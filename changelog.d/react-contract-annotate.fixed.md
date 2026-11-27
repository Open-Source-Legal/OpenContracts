- DOCX defects of the old renderer that the library does not have
  (documented in its README): structural annotations are drawn when "Show
  structural" is on (the old toggle projected nothing); documents with line
  breaks, tables or images get their annotations (the projection failed on
  their unclosed elements and showed none); annotations that cross a bold /
  plain run boundary at a space are drawn; selecting repeated text resolves
  to the occurrence selected; a zoomed page scrolls to its left edge; the
  projected HTML no longer gains a blank line and an indent.
