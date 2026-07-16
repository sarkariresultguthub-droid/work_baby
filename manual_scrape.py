# ============================================================
#  manual_scrape.py  —  Interactive CLI
#  Site choose karo → category choose karo → kitne latest posts
#  chahiye batao → scrape ho jayega → har post category-wali
#  folder ke andar, post-title ke naam se save hoga.
# ============================================================

import sys
from config import SITES
from scraper import manual_scrape


def show_site_menu():
    print("\n" + "=" * 50)
    print("  📋 MANUAL SCRAPER — Site Select Karo")
    print("=" * 50)
    for i, site in enumerate(SITES, 1):
        print(f"  {i}. {site['name']}  ({site['url']})")
    print(f"  {len(SITES) + 1}. 🌐 Custom URL (koi bhi naya site)")
    print("  0. Exit")
    print("=" * 50)


def get_site_choice():
    show_site_menu()
    while True:
        choice = input("\n👉 Site number daalo: ").strip()
        if choice == "0":
            sys.exit(0)
        if not choice.isdigit():
            print("❌ Sirf number daalo.")
            continue
        choice = int(choice)
        if 1 <= choice <= len(SITES):
            return SITES[choice - 1]
        elif choice == len(SITES) + 1:
            # Custom URL — naya site jo config mein nahi hai
            url = input("🔗 URL daalo (https:// ke saath): ").strip()
            category = input("🏷️  Category daalo (e.g. jobs/scholarships/general): ").strip() or "general"
            return {
                "name": url.split("//")[-1].split("/")[0],
                "url": url,
                "category": category,
                "categories": {},
            }
        else:
            print("❌ Galat number, dobara try karo.")


def get_category_choice(site_config: dict):
    """
    Site ke andar kaunsi listing-category scrape karni hai (jaise
    SarkariResult -> Latest Job / Admit Card / Results / Syllabus etc.)
    Returns: (category_label, category_url) — dono None agar site ke
    paas categories defined nahi hain (toh main url hi use hoga).
    """
    categories = site_config.get("categories") or {}

    if not categories:
        print(f"\nℹ️  '{site_config['name']}' ke liye koi sub-category defined nahi hai —")
        print(f"   seedha is site ke main page ko scrape karenge: {site_config['url']}")
        return None, None

    print("\n" + "-" * 50)
    print(f"  🗂️  '{site_config['name']}' ke andar Category Select Karo")
    print("-" * 50)
    labels = list(categories.keys())
    for i, label in enumerate(labels, 1):
        print(f"  {i}. {label}")
    print(f"  {len(labels) + 1}. 🏠 Home page (saari categories mix)")
    print("-" * 50)

    while True:
        choice = input("\n👉 Category number daalo: ").strip()
        if not choice.isdigit():
            print("❌ Sirf number daalo.")
            continue
        choice = int(choice)
        if 1 <= choice <= len(labels):
            label = labels[choice - 1]
            return label, categories[label]
        elif choice == len(labels) + 1:
            return "Home", site_config["url"]
        else:
            print("❌ Galat number, dobara try karo.")


def get_num_posts():
    while True:
        n = input("\n📊 Kitne latest posts scrape karne hain? (number daalo): ").strip()
        if n.isdigit() and int(n) > 0:
            return int(n)
        print("❌ Sahi number daalo (e.g. 5, 10, 20).")


if __name__ == "__main__":
    print("\n🕷️  Universal Manual Scraper")
    print("WordPress + Normal sites — dono support karta hai")
    print("Har post ab category-wali folder ke andar, title ke naam se save hoga.\n")

    while True:
        site_config = get_site_choice()
        category_label, category_url = get_category_choice(site_config)
        num_posts = get_num_posts()

        scrape_target = category_label or site_config["name"]
        print(f"\n⏳ Scraping '{site_config['name']}' → category '{scrape_target}' — latest {num_posts} posts...\n")

        result = manual_scrape(site_config, num_posts, category_label, category_url)

        if result:
            print(f"\n✅ DONE! {result['items_count']} posts scraped.")
            print(f"📁 Folder: {result['folder']}")
            print(f"   (har post apni alag file mein, post-title ke naam se saved hai)")
            print(f"\n➡️  Ab AI formatter chalao (poore folder ko ya kisi ek file ko):")
            print(f"   python ai_formatter.py \"{result['folder']}\"")
        else:
            print("\n❌ Scraping fail ho gaya. logs/scraper.log dekho.")

        again = input("\n🔄 Aur scrape karna hai? (y/n): ").strip().lower()
        if again != "y":
            print("\n👋 Bye!")
            break
