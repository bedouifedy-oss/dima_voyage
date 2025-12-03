# core/utils.py
import requests
from amadeus import Client, ResponseError
from django.urls import reverse

def send_visa_whatsapp(request, booking, lang):
    """
    Sends the Visa Form link via WhatsApp to the client.
    Returns: (bool: Success?, str: Message)
    """
    from core.models import WhatsAppSettings # Import inside to avoid circular dependency

    config = WhatsAppSettings.objects.first()
    if not config:
        return False, "❌ Error: WhatsApp Settings not configured."

    if not booking.client.phone:
        return False, f"⚠️ Error: No phone number found for {booking.client.name}."

    # Generate Link
    link = request.build_absolute_uri(reverse('public_visa_form', args=[booking.ref]))
    
    # Select Template
    msg_template = config.template_fr if lang == 'fr' else config.template_tn
    
    # Format Message
    try:
        msg = msg_template.format(
            client_name=booking.client.name, 
            link=link, 
            ref=booking.ref
        )
    except KeyError:
        msg = f"Hello {booking.client.name}, please upload your documents here: {link}"

    # Send via API
    try:
        payload = {
            "token": config.api_token,
            "to": booking.client.phone,
            "body": msg
        }
        response = requests.post(config.api_url, data=payload)
        
        if response.status_code == 200:
            return True, "Sent successfully."
        else:
            return False, f"API Error: {response.text}"
            
    except Exception as e:
        return False, f"Connection Error: {str(e)}"


def get_amadeus_client():
    """
    Helper function to load credentials from the Database dynamically.
    """
    # Import inside function to avoid "App Registry Not Ready" errors
    from core.models import AmadeusSettings

    config = AmadeusSettings.objects.first()

    if not config:
        print("❌ Error: Amadeus API Settings not configured in Admin.")
        return None

    try:
        # Initialize the client using the DB credentials
        return Client(
            client_id=config.client_id,
            client_secret=config.client_secret,
            hostname=config.environment,  # 'test' or 'production'
        )
    except Exception as e:
        print(f"❌ Error initializing Amadeus Client: {e}")
        return None


def search_airports(keyword):
    """
    Searches for airports and cities matching the keyword.
    Returns a list of dicts: [{'label': 'TUN - Carthage', 'value': 'TUN'}, ...]
    """
    # 1. Get the client from the DB
    amadeus = get_amadeus_client()

    if not amadeus:
        return []  # Fail gracefully if no config found

    print(f"🔍 Amadeus Searching for: {keyword}")

    try:
        response = amadeus.reference_data.locations.get(
            keyword=keyword,
            # Search for both Airports and Cities to improve results
            subType="AIRPORT,CITY",
        )

        results = []
        for location in response.data:
            # Ensure the location actually has an IATA code
            if "iataCode" in location:
                results.append(
                    {
                        "label": f"{location['iataCode']} - {location['name']}",
                        "value": location["iataCode"],  # This is what gets saved to DB
                    }
                )

        print(f"✅ Found {len(results)} locations")
        return results

    except ResponseError as error:
        print(f"❌ Amadeus API Error: {error}")
        return []
    except Exception as e:
        print(f"❌ Python Error: {e}")
        return []


# Notification Badge Logic
def badge_callback(request):
    from core.models import Announcement

    if not request.user.is_authenticated:
        return None

    count = Announcement.objects.exclude(acknowledged_by=request.user).count()
    return count
