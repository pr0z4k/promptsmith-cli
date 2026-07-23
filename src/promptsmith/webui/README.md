# webui - not planned for this cycle

This directory is an empty placeholder. It's not being implemented right
now, and there's no active plan to build a web interface for PromptSmith-cli
in the current development cycle.

PromptSmith-cli's design is deliberately local-only and terminal-based (see
the project's own "100% Open Source, Local Only, Zero Commercial
Dependencies" positioning). A web UI would mean running a local server
process at minimum, which is a real architectural shift worth a
deliberate decision, not something to grow accidentally out of an empty
stub someone finds later and assumes is half-built.

If a web interface becomes a real need, it should start as its own
proposal - not be built silently into this directory. Until then, this
file exists so this isn't mistaken for an abandoned half-finished
feature: it's an intentional placeholder, explicitly deferred.
