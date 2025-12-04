#!/usr/bin/env python3
"""
Backfill series_asin for all books in the library
This script will fetch metadata and update series_asin for books that don't have it
"""

import sys
import time
sys.path.insert(0, '/home/brandon/AuralArchive')

from services.audible.audible_catalog_service.audible_catalog_service import AudibleService
from services.database.database_service import DatabaseService

def backfill_series_asin():
    """Backfill series_asin for all books"""
    
    print("=" * 80)
    print("Backfilling series_asin for all books in library")
    print("=" * 80)
    
    # Initialize services
    audible_service = AudibleService()
    db_service = DatabaseService()
    
    # Get all books
    all_books = db_service.get_all_books()
    print(f"\nFound {len(all_books)} total books in library")
    
    # Filter books that need series_asin
    books_needing_update = []
    for book in all_books:
        asin = book.get('ASIN')
        series_asin = book.get('series_asin')
        series_name = book.get('Series', 'N/A')
        
        # Skip if no ASIN or already has series_asin
        if not asin or asin == 'N/A':
            continue
        if series_asin and series_asin != '':
            continue
        # Skip if not in a series
        if series_name == 'N/A' or not series_name:
            continue
            
        books_needing_update.append(book)
    
    print(f"Found {len(books_needing_update)} books that need series_asin")
    
    if not books_needing_update:
        print("\n✓ All books already have series_asin or are not in a series!")
        return
    
    # Process each book
    updated = 0
    failed = 0
    no_series = 0
    
    for idx, book in enumerate(books_needing_update, 1):
        book_id = book.get('ID')
        asin = book.get('ASIN')
        title = book.get('Title', 'Unknown')
        series_name = book.get('Series', 'N/A')
        
        print(f"\n[{idx}/{len(books_needing_update)}] Processing: {title}")
        print(f"   Series: {series_name}")
        print(f"   ASIN: {asin}")
        
        try:
            # Search for book metadata
            search_results = audible_service.search_books(asin, region="us", num_results=5)
            
            if not search_results:
                print(f"   ❌ No results found")
                failed += 1
                continue
            
            # Get first result
            book_data = search_results[0]
            extracted_series_asin = book_data.get('series_asin')
            
            if not extracted_series_asin:
                print(f"   ℹ️  No series_asin found in API response")
                no_series += 1
                continue
            
            print(f"   ✓ Found series_asin: {extracted_series_asin}")
            
            # Update database
            import sqlite3
            conn = sqlite3.connect('/home/brandon/AuralArchive/database/auralarchive_database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE books SET series_asin = ? WHERE id = ?", (extracted_series_asin, book_id))
            conn.commit()
            conn.close()
            
            print(f"   ✓ Updated database")
            updated += 1
            
            # Rate limiting - 500ms delay between requests
            if idx < len(books_needing_update):
                time.sleep(0.5)
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed += 1
            continue
    
    print("\n" + "=" * 80)
    print("Backfill Summary:")
    print(f"  Total processed: {len(books_needing_update)}")
    print(f"  ✓ Updated: {updated}")
    print(f"  ℹ️  No series_asin available: {no_series}")
    print(f"  ❌ Failed: {failed}")
    print("=" * 80)

if __name__ == "__main__":
    try:
        backfill_series_asin()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
