# Electrical Safety: Wearable and Body-Worn Devices

Any prototype device intended to be worn on or attached to a person's body
must be powered by a battery or an isolated, current-limited supply --
never connected directly to benchtop AC mains or any non-isolated power
source. This applies even if the device's own components (e.g. a
microcontroller such as an ESP32) are individually low-voltage-rated: the
hazard is the combination of a body-worn conductor path with an
unisolated mains connection, not the rating of any single component.

Bench power supplies used for testing body-worn prototypes must go
through galvanic isolation (an isolation transformer or a certified
isolated bench supply) before any connection to a device that will be worn
during testing. Testing a wearable prototype's electronics on a bench,
unworn, is a separate activity from testing it while worn -- the isolation
requirement applies specifically to the worn condition.

Questions about combining body-worn hardware with any AC-connected supply
should go to the lab's electrical safety officer before proceeding, even
if each individual component seems low-risk in isolation.
