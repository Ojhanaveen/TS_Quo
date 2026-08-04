"""CSS/XPath selectors for the sites we scrape.

Kept in one place because these break the moment either site ships a
front-end change -- isolating them here means a broken selector is a
one-line fix, not a hunt through scraper logic.
"""

# twitter.com / x.com (search, "Latest" tab)
X_TWEET_ARTICLE = "article[data-testid='tweet']"
X_TWEET_TEXT = "div[data-testid='tweetText']"
X_USERNAME = "div[data-testid='User-Name'] a[role='link']"
X_TIMESTAMP = "time"
X_LIKE = "div[data-testid='like'] span"
X_RETWEET = "div[data-testid='retweet'] span"
X_REPLY = "div[data-testid='reply'] span"
X_RATE_LIMIT_BANNER = "//*[contains(text(), 'Rate limit') or contains(text(), 'Something went wrong')]"
X_LOGIN_WALL = "//*[contains(text(), 'Log in') and contains(text(), 'to see')]"

# Nitter mirrors (fallback, no login wall, HTML is simpler/more stable)
NITTER_TWEET = "div.timeline-item"
NITTER_USERNAME = "a.username"
NITTER_TIMESTAMP = "span.tweet-date a"
NITTER_TEXT = "div.tweet-content"
NITTER_STATS = "div.tweet-stats span.tweet-stat"
