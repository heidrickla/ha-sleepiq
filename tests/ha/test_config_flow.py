"""The config flow: import, user setup and its failures, the duplicate guard, reauth.

Vendored from core's tests/components/sleepiq/test_config_flow.py at tag
2026.8.2 and extended: every step that can show an error is also driven past
it, and every form with a password field is checked to mask it and not echo it.
"""

from unittest.mock import AsyncMock, patch

from asyncsleepiq import SleepIQLoginException, SleepIQTimeoutException
import pytest
import voluptuous as vol
from homeassistant import config_entries, setup
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import TextSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sleepiq.const import DOMAIN

from .conftest import SLEEPIQ_CONFIG, setup_platform

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


def _password_is_masked_and_not_echoed(result) -> None:
    """The password field is a password selector with no default or suggestion."""
    for key, validator in result["data_schema"].schema.items():
        if key == CONF_PASSWORD:
            break
    else:
        pytest.fail("no password field on the form")
    assert key.default is vol.UNDEFINED
    assert (key.description or {}).get("suggested_value") in (None, "")
    assert isinstance(validator, TextSelector)
    assert validator.config["type"] == "password"


# ------------------------------------------------------------------- import


async def test_import(hass: HomeAssistant) -> None:
    """Test that we can import a config entry."""
    with patch("asyncsleepiq.AsyncSleepIQ.login"):
        assert await setup.async_setup_component(hass, DOMAIN, {DOMAIN: SLEEPIQ_CONFIG})
        await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_USERNAME] == SLEEPIQ_CONFIG[CONF_USERNAME]
    assert entry.data[CONF_PASSWORD] == SLEEPIQ_CONFIG[CONF_PASSWORD]


@pytest.mark.parametrize(
    "side_effect", [SleepIQLoginException, SleepIQTimeoutException]
)
async def test_import_failure(hass: HomeAssistant, side_effect) -> None:
    """Test that we won't import a config entry on login failure."""
    with patch(
        "asyncsleepiq.AsyncSleepIQ.login",
        side_effect=side_effect,
    ):
        assert await setup.async_setup_component(hass, DOMAIN, {DOMAIN: SLEEPIQ_CONFIG})
        await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0


# --------------------------------------------------------------------- user


async def test_show_set_form(hass: HomeAssistant) -> None:
    """Test that the setup form is served."""
    with patch("asyncsleepiq.AsyncSleepIQ.login"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=None
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    _password_is_masked_and_not_echoed(result)


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (SleepIQLoginException, "invalid_auth"),
        (SleepIQTimeoutException, "cannot_connect"),
    ],
)
async def test_login_failure_then_the_same_flow_recovers(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, side_effect, error
) -> None:
    """Each login failure maps to its message, and a retry finishes the flow."""
    with patch(
        "asyncsleepiq.AsyncSleepIQ.login",
        side_effect=side_effect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=SLEEPIQ_CONFIG
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}
    # The username comes back for correction; the password never does.
    _password_is_masked_and_not_echoed(result)

    with patch("asyncsleepiq.AsyncSleepIQ.login", return_value=None):
        done = await hass.config_entries.flow.async_configure(
            result["flow_id"], SLEEPIQ_CONFIG
        )
        await hass.async_block_till_done()

    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"] == SLEEPIQ_CONFIG
    assert done["result"].unique_id == SLEEPIQ_CONFIG[CONF_USERNAME].lower()
    assert len(mock_setup_entry.mock_calls) == 1


async def test_success(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test successful flow provides entry creation data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    with patch("asyncsleepiq.AsyncSleepIQ.login", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], SLEEPIQ_CONFIG
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == SLEEPIQ_CONFIG[CONF_USERNAME]
    assert result2["data"][CONF_USERNAME] == SLEEPIQ_CONFIG[CONF_USERNAME]
    assert result2["data"][CONF_PASSWORD] == SLEEPIQ_CONFIG[CONF_PASSWORD]
    assert len(mock_setup_entry.mock_calls) == 1


async def test_the_same_account_is_not_added_twice(hass: HomeAssistant) -> None:
    """A second entry for the account aborts, whatever the letter case."""
    MockConfigEntry(
        domain=DOMAIN,
        data=SLEEPIQ_CONFIG,
        unique_id=SLEEPIQ_CONFIG[CONF_USERNAME].lower(),
    ).add_to_hass(hass)

    with patch("asyncsleepiq.AsyncSleepIQ.login"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={**SLEEPIQ_CONFIG, CONF_USERNAME: "User@Email.com"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ------------------------------------------------------------------- reauth


async def test_reauth_password(hass: HomeAssistant) -> None:
    """Test reauth form."""
    entry = await setup_platform(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    _password_is_masked_and_not_echoed(result)

    with patch(
        "custom_components.sleepiq.config_flow.AsyncSleepIQ.login",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PASSWORD: "password"},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (SleepIQLoginException, "invalid_auth"),
        (SleepIQTimeoutException, "cannot_connect"),
    ],
)
async def test_reauth_failure_then_the_same_flow_recovers(
    hass: HomeAssistant, side_effect, error
) -> None:
    """A rejected password shows the form again; the right one finishes reauth."""
    entry = await setup_platform(hass)
    result = await entry.start_reauth_flow(hass)

    with patch("asyncsleepiq.AsyncSleepIQ.login", side_effect=side_effect):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "wrong"}
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2["errors"] == {"base": error}
    _password_is_masked_and_not_echoed(result2)

    with patch("asyncsleepiq.AsyncSleepIQ.login", return_value=None):
        done = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "rotated"}
        )
        await hass.async_block_till_done()

    assert done["type"] is FlowResultType.ABORT
    assert done["reason"] == "reauth_successful"
    assert entry.data[CONF_USERNAME] == SLEEPIQ_CONFIG[CONF_USERNAME]
    assert entry.data[CONF_PASSWORD] == "rotated"
