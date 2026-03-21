"""
items.py — Definição dos Items Scrapy para o WebScraper Jurídico

Define a estrutura de dados que flui pelo pipeline do Scrapy.
Cada item coletado pelos spiders é representado por ScrapedItem.
"""

import scrapy


class ScrapedItem(scrapy.Item):
    """
    Item principal coletado pelos spiders.

    Campos obrigatórios:
    - url: URL de onde o item foi extraído
    - domain: domínio da URL (calculado automaticamente)
    - job_id: ID do job de scraping que gerou este item
    - spider_name: nome do spider que coletou o item
    - scraped_at: timestamp da coleta (ISO 8601)

    Campos opcionais de conteúdo:
    - title: título da página ou item
    - content: texto limpo extraído
    - raw_data: dados brutos (HTML ou JSON) antes do processamento
    - metadata: dicionário com campos extras extraídos dinamicamente
    """

    # ── Campos de identificação ─────────────────────────────────────────────
    url = scrapy.Field()            # URL de origem do item
    domain = scrapy.Field()         # Domínio extraído da URL
    job_id = scrapy.Field()         # ID do job que iniciou o scraping
    spider_name = scrapy.Field()    # Nome do spider utilizado

    # ── Campos de conteúdo ──────────────────────────────────────────────────
    title = scrapy.Field()          # Título da página ou artigo
    content = scrapy.Field()        # Texto limpo extraído
    raw_data = scrapy.Field()       # Dados brutos (HTML/JSON) originais

    # ── Metadados de coleta ─────────────────────────────────────────────────
    scraped_at = scrapy.Field()     # Timestamp ISO 8601 da coleta
    metadata = scrapy.Field()       # Campos extras em formato dict
