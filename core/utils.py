# core/utils.py
from amadeus import Client, ResponseError


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
