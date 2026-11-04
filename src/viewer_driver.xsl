<?xml version="1.0" encoding="UTF-8"?>
<!-- Führt die zwei Schritte der KoSIT-Visualisierung in einem Java-Prozess aus: Syntax (CII/UBL) → neutrales Modell → HTML. -->
<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xsl:param name="base" as="xs:string"/>
  <xsl:param name="to" as="xs:string"/>
  <xsl:param name="lang" as="xs:string" select="'de'"/>
  <xsl:output method="html" html-version="5" encoding="UTF-8"/>
  <xsl:template match="/">
    <xsl:variable name="model" select="transform(map{'stylesheet-location': $base || '/' || $to, 'source-node': .})?output"/>
    <xsl:sequence select="transform(map{'stylesheet-location': $base || '/xrechnung-html.xsl', 'source-node': $model,
                          'stylesheet-params': map{QName('', 'lang'): $lang}})?output"/>
  </xsl:template>
</xsl:stylesheet>
