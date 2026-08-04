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
# Tag-agnostic ([data-testid=...] not div[data-testid=...]): the action
# buttons render as <button>, and the count is read from the element's
# aria-label rather than its inner spans -- the nested span structure
# around the icon/number changes across X front-end deploys, but the
# aria-label ("1.2K Likes. Like") has stayed stable.
X_LIKE = "[data-testid='like'], [data-testid='unlike']"
X_RETWEET = "[data-testid='retweet'], [data-testid='unretweet']"
X_REPLY = "[data-testid='reply']"
X_RATE_LIMIT_BANNER = "//*[contains(text(), 'Rate limit') or contains(text(), 'Something went wrong')]"
X_LOGIN_WALL = "//*[contains(text(), 'Log in') and contains(text(), 'to see')]"

# Nitter mirrors (fallback, no login wall, HTML is simpler/more stable)
NITTER_TWEET = "div.timeline-item"
NITTER_USERNAME = "a.username"
NITTER_TIMESTAMP = "span.tweet-date a"
NITTER_TEXT = "div.tweet-content"
NITTER_STATS = "div.tweet-stats span.tweet-stat"
