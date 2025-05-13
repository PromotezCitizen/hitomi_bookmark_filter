package com.example.hentoidbookmark

data class HentoidExport(
    val bookmarks: List<HentoidBookmark>
)
data class HentoidBookmark(
    val site: String,
    val title: String,
    var url: String,
    val order: Int,
)
data class QueryState(
    var area: String,
    var tag: String,
    var language: String,
    val orderby: String,
    val orderbykey: String,
    val orderbydirection: String
)


