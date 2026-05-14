#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LibGen Client with Automatic Mirror Management
Supports searching and downloading books with fallback between multiple mirrors.
Mirrors are cached in a local file for faster subsequent runs.
"""

import os
import sys
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ----------------------------- Configuration -----------------------------
# لیست اولیه mirrorهای LibGen (بر اساس دانش فعلی)
DEFAULT_MIRRORS = [
    "https://libgen.is",
    "https://libgen.st",
    "https://libgen.li",
    "https://libgen.rs",
    "http://libgen.lc",
    "https://libgen.gs",
]

CACHE_FILE = os.path.join(os.path.dirname(__file__), "mirrors.json")
WORKING_MIRROR_KEY = "last_working_mirror"
ALL_WORKING_MIRRORS_KEY = "working_mirrors"

# -------------------------------------------------------------------------

class LibGenClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.working_mirrors = []
        self.last_working_mirror = None
        self._load_cache()

    def _load_cache(self):
        """بارگذاری mirrorهای ذخیره شده از فایل کش"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    self.last_working_mirror = data.get(WORKING_MIRROR_KEY)
                    self.working_mirrors = data.get(ALL_WORKING_MIRRORS_KEY, [])
                print(f"📂 Cache loaded: last mirror = {self.last_working_mirror}")
            except Exception as e:
                print(f"⚠️ Could not load cache: {e}")

    def _save_cache(self):
        """ذخیره mirrorهای فعال در فایل کش"""
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump({
                    WORKING_MIRROR_KEY: self.last_working_mirror,
                    ALL_WORKING_MIRRORS_KEY: self.working_mirrors
                }, f, indent=2)
            print(f"💾 Cache saved: {self.last_working_mirror}")
        except Exception as e:
            print(f"⚠️ Could not save cache: {e}")

    def _test_mirror(self, mirror):
        """تست اینکه آیا یک mirror پاسخ می‌دهد و صفحه جستجو را نمایش می‌دهد"""
        test_url = urljoin(mirror, "/search.php?req=test")
        try:
            resp = self.session.get(test_url, timeout=10)
            if resp.status_code == 200 and "libgen" in resp.text.lower():
                return True
        except:
            pass
        return False

    def _get_ordered_mirrors(self):
        """لیست mirrorها به ترتیب اولویت: آخرین mirror موفق، سپس mirrorهای موفق قبلی، سپس mirrorهای پیش‌فرض"""
        ordered = []
        if self.last_working_mirror and self.last_working_mirror not in ordered:
            ordered.append(self.last_working_mirror)
        for m in self.working_mirrors:
            if m not in ordered:
                ordered.append(m)
        for m in DEFAULT_MIRRORS:
            if m not in ordered:
                ordered.append(m)
        return ordered

    def _find_working_mirror(self):
        """پیدا کردن یک mirror کاری از بین لیست اولویت‌بندی شده"""
        mirrors_to_try = self._get_ordered_mirrors()
        print("🔍 Searching for a working LibGen mirror...")
        for mirror in mirrors_to_try:
            print(f"   Testing {mirror} ... ", end="")
            if self._test_mirror(mirror):
                print(" ✅")
                # به‌روزرسانی کش
                if mirror not in self.working_mirrors:
                    self.working_mirrors.append(mirror)
                self.last_working_mirror = mirror
                self._save_cache()
                return mirror
            else:
                print(" ❌")
        return None

    def search(self, query):
        """جستجو با استفاده از mirror کاری. اگر mirror فعلی جواب نداد، به mirror بعدی سوئیچ می‌کند."""
        mirror = self._find_working_mirror()
        if not mirror:
            raise Exception("❌ No working LibGen mirror found. Please check your internet or update mirrors list.")

        search_url = urljoin(mirror, f"/search.php?req={query}&lg_topic=libgen&open=0&view=simple&res=25&phrase=1&column=def")
        try:
            resp = self.session.get(search_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            # اگر این mirror خاص در جستجو کار نکرد، آن را از لیست کاری حذف کرده و دوباره تلاش کن
            print(f"⚠️ Mirror {mirror} failed during search: {e}. Removing from working list and retrying...")
            if mirror in self.working_mirrors:
                self.working_mirrors.remove(mirror)
            if self.last_working_mirror == mirror:
                self.last_working_mirror = None
            self._save_cache()
            return self.search(query)  # recursion با mirror جدید

        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table', {'class': 'c'})
        if not table:
            print(f"⚠️ Mirror {mirror} returned no results table. Trying next mirror...")
            if mirror in self.working_mirrors:
                self.working_mirrors.remove(mirror)
            if self.last_working_mirror == mirror:
                self.last_working_mirror = None
            self._save_cache()
            return self.search(query)

        rows = table.find_all('tr')[1:]
        books = []
        for idx, row in enumerate(rows, start=1):
            cols = row.find_all('td')
            if len(cols) < 8:
                continue
            title = cols[2].get_text(strip=True)
            author = cols[1].get_text(strip=True)
            year = cols[4].get_text(strip=True)
            publisher = cols[5].get_text(strip=True)
            # استخراج لینک دانلود
            download_link = None
            download_cell = cols[-1]
            link_tag = download_cell.find('a', href=True)
            if link_tag and 'href' in link_tag.attrs:
                download_link = link_tag['href']
                # اگر لینک نسبی بود، کاملش کن
                if download_link.startswith('/'):
                    download_link = urljoin(mirror, download_link)
            books.append({
                'index': idx,
                'title': title,
                'author': author,
                'year': year,
                'publisher': publisher,
                'download_url': download_link,
                'mirror': mirror  # ذخیره mirror مبدأ برای دانلود احتمالی
            })
        return books

    def download_book(self, book, save_path='downloads'):
        """دانلود کتاب با استفاده از mirror مرتبط. در صورت شکست لینک، mirror دیگری را امتحان می‌کند."""
        if not book.get('download_url'):
            print("❌ No download link available for this book.")
            return False

        # ابتدا سعی کن با همان mirror دانلود کنی
        success = self._attempt_download(book['download_url'], save_path, book['title'])
        if success:
            return True

        # اگر نشد، ممکن است لینک منقضی شده باشد. سعی کن کتاب را دوباره جستجو کرده و لینک جدید بگیر
        print("⚠️ Direct download failed. Re-searching the book to get fresh link...")
        fresh_books = self.search(book['title'])
        for b in fresh_books:
            if b['title'].strip().lower() == book['title'].strip().lower() and b['author'].strip().lower() == book['author'].strip().lower():
                if b.get('download_url'):
                    print("🔄 Found fresh link. Retrying download...")
                    return self._attempt_download(b['download_url'], save_path, book['title'])
        print("❌ Could not find a working download link after retry.")
        return False

    def _attempt_download(self, url, save_path, title):
        """عملیات واقعی دانلود با مدیریت خطا"""
        try:
            resp = self.session.get(url, stream=True, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            print(f"Download error: {e}")
            return False

        # استخراج نام فایل
        content_disp = resp.headers.get('content-disposition')
        if content_disp:
            filename = re.findall("filename=(.+)", content_disp)[0].strip('"')
        else:
            # ایجاد نام فایل از عنوان کتاب
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
            filename = f"{safe_title}.pdf"

        os.makedirs(save_path, exist_ok=True)
        filepath = os.path.join(save_path, filename)

        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"✅ Downloaded successfully: {filepath}")
        return True

# ----------------------------- Main CLI ---------------------------------

def main():
    search_term = os.environ.get('SEARCH_TERM')
    book_index_str = os.environ.get('BOOK_INDEX', '').strip()

    if not search_term:
        print("❌ Please provide SEARCH_TERM environment variable.")
        sys.exit(1)

    client = LibGenClient()

    print(f"🔎 Searching for: {search_term}")
    books = client.search(search_term)

    if not books:
        print("❌ No books found. Try a different search term or check mirrors.")
        sys.exit(1)

    if not book_index_str:
        # نمایش لیست کتاب‌ها
        print("\n📚 Search results:")
        for b in books:
            print(f"[{b['index']}] {b['title']} - {b['author']} ({b['year']}) - {b['publisher']}")
        print("\n💡 To download, run the workflow again and provide the book index in 'book_index' field.")
        sys.exit(0)

    # دانلود کتاب با ایندکس مشخص
    try:
        idx = int(book_index_str)
    except ValueError:
        print("❌ book_index must be an integer.")
        sys.exit(1)

    selected = next((b for b in books if b['index'] == idx), None)
    if not selected:
        print(f"❌ Book with index {idx} not found in search results.")
        sys.exit(1)

    print(f"⬇️ Downloading: {selected['title']} by {selected['author']}")
    success = client.download_book(selected, save_path='downloads')
    if success:
        print("🎉 Done. File saved in 'downloads' folder.")
        sys.exit(0)
    else:
        print("❌ Download failed after multiple attempts.")
        sys.exit(1)

if __name__ == "__main__":
    main()
