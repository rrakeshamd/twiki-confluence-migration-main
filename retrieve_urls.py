def retrieve_urls():
    # Takes twiki urls from twiki_urls.txt
    with open('twiki_urls.txt', 'r') as file:
        urls = []
        for line in file:
            line = line.strip()
            if not line:
                continue
            if line.startswith("# skip from here onwards"):
                break
            urls.append(line)
    return urls


if __name__ == "__main__":
    twiki_urls = retrieve_urls()
    print(twiki_urls)

