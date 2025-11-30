# core/utils.py
from amadeus import Client, ResponseError

# Initialize Amadeus
amadeus = Client(
    client_id='TlTNN6KZrzSA8F4dJuMEkP9MYT8eBq06',
    client_secret='18FSIfnCLFYJCv9d',
    hostname='test' 
)

def search_airports(keyword):
    """
    Searches for airports and cities matching the keyword.
    Returns a list of dicts: [{'label': 'TUN - Carthage', 'value': 'TUN'}, ...]
    """
    print(f"🔍 Amadeus Searching for: {keyword}")

    try:
        response = amadeus.reference_data.locations.get(
            keyword=keyword,
            # UPDATED: Search for both Airports and Cities to improve results
            subType='AIRPORT,CITY' 
        )
        
        results = []
        for location in response.data:
            # Ensure the location actually has an IATA code (some obscure spots don't)
            if 'iataCode' in location:
                results.append({
                    'label': f"{location['iataCode']} - {location['name']}",
                    'value': location['iataCode'] # This is what gets saved to DB
                })
            
        print(f"✅ Found {len(results)} locations")
        return results
        
    except ResponseError as error:
        print(f"❌ Amadeus Error: {error}")
        return []
    except Exception as e:
        print(f"❌ Python Error: {e}")
        return []

# Notification Badge Logic
def badge_callback(request):
    from core.models import Announcement
    
    if not request.user.is_authenticated:
        return None

    # Count announcements where the user is NOT in the 'acknowledged_by' list
    count = Announcement.objects.exclude(acknowledged_by=request.user).count()
    
    if count == 0:
        return None 
        
    return count
