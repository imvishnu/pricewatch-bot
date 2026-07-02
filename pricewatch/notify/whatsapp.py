"""WhatsApp notifier — STUB, not implemented yet.

To add WhatsApp as a second alert channel later, implement Notifier using
the WhatsApp Business Cloud API. Key constraint to design around:

  The Cloud API only allows free-form messages within a 24-hour customer
  service window (opened by the *user* messaging the business). Outside
  that window — which is the normal case for price alerts fired by a
  poller — you MUST use a pre-approved template message (message type
  "template"), so the alert format has to be registered as a template
  with placeholders (product title, price, drop %) in advance.

Sketch:

# import httpx
# from .base import Notifier
#
# class WhatsAppNotifier(Notifier):
#     def __init__(self, access_token: str, phone_number_id: str,
#                  template_name: str = "price_drop_alert"):
#         self._url = (f"https://graph.facebook.com/v20.0/"
#                      f"{phone_number_id}/messages")
#         self._token = access_token
#         self._template = template_name
#
#     async def send(self, recipient: str, text: str) -> bool:
#         # recipient: E.164 phone number. Because of the 24-hour-window
#         # rule, send a *template* message, not free-form text:
#         # {"messaging_product": "whatsapp", "to": recipient,
#         #  "type": "template",
#         #  "template": {"name": self._template,
#         #               "language": {"code": "en"},
#         #               "components": [{"type": "body", "parameters":
#         #                   [{"type": "text", "text": text}]}]}}
#         raise NotImplementedError
"""
