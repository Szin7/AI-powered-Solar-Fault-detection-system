# Automatic technician alerts

The fault classifier identifies supported patterns. Incident rules decide when a fault starts or recovers, and a delivery worker contacts the technician assigned to that station. An extra LLM is not needed to send a reliable notification. Recommended actions are deterministic rules, not remotely verified repairs.

## Demonstrate without an account or hardware

Run the demo, sign in with the operator key, select a station and find **Technician alerts**. Enter the technician's name and international phone number (a Nepal number starts with +977), select WhatsApp or SMS, enable automatic alerts, enable **Include simulated incidents**, and save.

Choose an open-circuit preset in the simulator. After the model stabilizes, the alert list records one preview with the station, fault, model score, recommended action and event time. Continued readings of the same open incident do not create a message each time. A later confirmed recovery creates another alert. **Preview message** displays the latest prediction's message immediately and sends nothing. Saving a contact applies only to future incident transitions.

`TECHNICIAN_DELIVERY` defaults to `preview`. Preview alerts stay previews even if live mode is enabled later. Simulated events are excluded unless the operator explicitly enables them; messages identify simulation. Contacts and delivery records are stored in the local database under ignored `var/`, not committed to GitHub. Viewer access masks the stored phone number.

## Send real SMS

Use a Twilio account, an SMS-capable sender and a destination supported by that account. Trial accounts may require a verified destination. In the terminal that will run the backend, set values without putting the token into the command history:

```bash
cd /mnt/d/Projects/SolarSense
source .venv/bin/activate
read -r -p 'Twilio account SID: ' TWILIO_ACCOUNT_SID
read -r -s -p 'Twilio auth token: ' TWILIO_AUTH_TOKEN
printf '\n'
read -r -p 'SMS sender in international format: ' TWILIO_SMS_FROM
export TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_SMS_FROM
export TECHNICIAN_DELIVERY=live
python -m solarsense demo
```

Select SMS in the dashboard, save the enabled contact, and create a new incident. Use `serve` instead of `demo` for your hardware session, retaining the hardware environment settings. Keep **Include simulated incidents** off when only physical-device events should contact the technician. This app uses direct HTTPS requests; provider account restrictions, connectivity and destination coverage can still prevent delivery.

## Send real WhatsApp

Use a Twilio WhatsApp sender and an approved WhatsApp notification template. The integration uses ContentSid and ContentVariables so it can initiate a notification outside an existing conversation. Configure the account SID and auth token as above, then:

```bash
read -r -p 'WhatsApp sender in international format: ' TWILIO_WHATSAPP_FROM
read -r -p 'Approved template Content SID: ' TWILIO_CONTENT_SID
export TWILIO_WHATSAPP_FROM TWILIO_CONTENT_SID
export TECHNICIAN_DELIVERY=live
python -m solarsense demo
```

Create an approved template whose variables have this meaning:

```text
SolarSense station {{1}}: {{2}} — {{3}}. Recommended action: {{4}}.
```

Variable 1 is the station ID, 2 is fault/recovery, 3 is the fault label, and 4 is the recommended action (prefixed SIMULATED for simulated incidents). Use the technician's agreed WhatsApp destination. Select WhatsApp in the contact form. SMS and WhatsApp share the same account but use separate sender settings. WhatsApp delivery does not open a browser tab or depend on an active WhatsApp Web login.

Provider documentation: [Twilio WhatsApp notification templates](https://www.twilio.com/docs/whatsapp/tutorial/send-whatsapp-notification-messages-templates) and [sending Content templates](https://www.twilio.com/docs/content/send-templates-created-with-the-content-template-builder). Account setup, sender activation, template approval and messaging charges are external to this repository.

## Delivery states and failures

| State | Meaning |
| --- | --- |
| preview | Recorded locally; never submitted to the provider. |
| pending | Queued for submission. |
| submitting | A submission is in progress. |
| submitted | Provider supplied a message ID; delivery is not confirmed yet. |
| delivered | Provider reports delivered/read. It does not prove a repair was completed. |
| failed | Provider rejected the request/delivery, or safe connection retries were exhausted. |
| uncertain | A timeout/crash left submission ambiguous, or delivery was not confirmed within 24 hours. Check the provider before repeating. |
| cancelled | Contact was disabled, reassigned or made ineligible before submission. |

The worker persists jobs and claims submissions before contacting Twilio. Connection failures before submission and rate limiting have bounded retries. Ambiguous submission timeouts are not automatically resent. A failed delivery-status poll never triggers another POST. Status checks begin after 30 seconds and back off up to five minutes. Delivery work runs separately from inference so a slow provider does not block sensor processing. Turning off a contact prevents pending submissions but cannot recall messages already accepted by the provider.

Tests exercise both message formats, incident-triggered previews, masking, duplicate suppression, submission versus delivery, status polling and ambiguous timeouts using a mock HTTP provider. No real technician message was sent during implementation; credentials and an actual destination are needed for a live acceptance test.
