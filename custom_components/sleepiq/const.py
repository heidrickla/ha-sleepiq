"""Define constants for the SleepIQ component."""

DATA_SLEEPIQ = "data_sleepiq"
DOMAIN = "sleepiq"

ACTUATOR = "actuator"
CORE_CLIMATE_TIMER = "core_climate_timer"
CORE_CLIMATE = "core_climate"
BED = "bed"
FIRMNESS = "firmness"
IS_IN_BED = "is_in_bed"
# The bed's own pressure reading. Core takes this from homeassistant.const,
# which is a deprecated home for it; the string is the same either way and it
# is this integration's entity type, so it lives here.
PRESSURE = "pressure"
SLEEP_NUMBER = "sleep_number"
FOOT_WARMING_TIMER = "foot_warming_timer"
FOOT_WARMER = "foot_warmer"
SLEEP_SCORE = "sleep_score"
SLEEP_DURATION = "sleep_duration"
HEART_RATE = "heart_rate"
RESPIRATORY_RATE = "respiratory_rate"
HRV = "hrv"
MASSAGE_MODE = "massage_mode"
MASSAGE_FOOT_SPEED = "massage_foot_speed"
MASSAGE_HEAD_SPEED = "massage_head_speed"
MASSAGE_TIMER = "massage_timer"

# Translation keys for the entities whose name is not built from the type
# constant above. Every entity name comes from strings.json.
LIGHT = "light"
PAUSE_MODE = "pause_mode"
PRESET = "preset"
HEART_RATE_AVG = "heart_rate_avg"
RESPIRATORY_RATE_AVG = "respiratory_rate_avg"

# Repair issues this integration raises, one key per issue.
ISSUE_DEPRECATED_YAML = "deprecated_yaml"

LEFT = "left"
RIGHT = "right"
SIDES = [LEFT, RIGHT]

SLEEPIQ_DATA = "sleepiq_data"
SLEEPIQ_STATUS_COORDINATOR = "sleepiq_status"
