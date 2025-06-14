package com.example.hentoidbookmark

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import android.util.Log
import android.view.View
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.io.File
import java.io.FileOutputStream

class MainActivity : AppCompatActivity() {
    private lateinit var openJsonFileLauncher: ActivityResultLauncher<Intent>

    private var negativeTerms: List<String> = emptyList()
    private var artists: List<String> = emptyList()
    private val httpClient = OkHttpClient()
    private val negativeResultSet = mutableSetOf<Int>()
    private val mainScope = MainScope()
    private var requestResult: List<Pair<String, Int>> = emptyList()
    private var openFileUri: Uri? = null

    private lateinit var loadBtn: View
    private lateinit var reqBtn: View
    private lateinit var saveBtn: View
    private lateinit var loadingOverlay: View

    private val originState: QueryState = QueryState("all", "index", "all", "date", "added", "desc")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.main)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        negativeTerms = getNegativeTags(this)

        loadBtn = findViewById<android.widget.Button>(R.id.btnLoad)
        reqBtn = findViewById<android.widget.Button>(R.id.btnReq)
        saveBtn = findViewById<android.widget.Button>(R.id.btnSave)
        loadingOverlay = findViewById<android.widget.ProgressBar>(R.id.loadingOverlay)

        loadBtn.setOnClickListener {
            artists = emptyList()
            reqBtn.isEnabled = false
            saveBtn.isEnabled = false

            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "application/json"
            }
            openJsonFileLauncher.launch(intent)
        }
        reqBtn.setOnClickListener {
            negativeResultSet.clear()
            requestResult = emptyList()
            showLoading(true)
            mainScope.launch {
                generateNegativeResultSet()
                requestResult = doSearch().sortedBy { it.second }

                showLoading(false)
                saveBtn.isEnabled = true
            }
        }
        saveBtn.setOnClickListener {
            saveJsonOutput()
        }

        reqBtn.isEnabled = false
        saveBtn.isEnabled = false

        openJsonFileLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                result.data?.data?.let { uri ->
                    val content = contentResolver.openInputStream(uri)
                        ?.bufferedReader()
                        ?.use { it.readText() } ?: throw IOException("파일 읽기 실패")
                    val export = Gson().fromJson(content, HentoidExport::class.java)
                    artists = export.bookmarks.map { bookmark -> convertUrl(bookmark.url) }
                        .toSet()
                        .toList()
                    openFileUri = uri
                    Log.d("Hentoid-Loading", artists.toString())
                }
                reqBtn.isEnabled = true
            }
        }

        requestStoragePermission()
    }

    private fun requestStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (!Environment.isExternalStorageManager()) {
                val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                val uri = Uri.fromParts("package", packageName, null)
                intent.data = uri
                startActivity(intent)
            }
        }
    }

    private fun showLoading(isLoading: Boolean) {
        loadingOverlay.visibility = if (isLoading) View.VISIBLE else View.GONE
        listOf(loadBtn, reqBtn).forEach { it.isEnabled = !isLoading }
    }

    private fun convertUrl(url: String): String {
        val prefixRemoved = url.replace("https://hitomi.la/", "")
        val artistOrGroup = if (prefixRemoved.startsWith("search.html")) {
            var removed = prefixRemoved.removePrefix("search.html?")
                .split("%20")
                .firstOrNull()
                ?.replace("%3A", ":") ?: ""
            while (removed.contains("%25"))
                removed = removed.replaceFirst("%25", "%")
            removed
        } else {
            prefixRemoved.removeSuffix("-all.html").replaceFirst("/", ":")
        }
        return artistOrGroup.replace("%2D", "-").replace("%20", "_")
    }

    private fun getNegativeTags(context: Context): List<String> {
        val inputStream = context.assets.open("negative_list.txt")
        return inputStream.bufferedReader().readLines().map { tag -> "-${tag.trim()}" }
    }

    private suspend fun generateNegativeResultSet() {
        val mutex = Mutex()
        coroutineScope {
            negativeTerms.map { term ->
                async(Dispatchers.IO) {
                    try {
                        val queryResult = getGalleryIdsForQuery(term.replace("-", ""), originState.copy())
                        queryResult?.forEach { item ->
                            mutex.withLock {
                                negativeResultSet.add(item)
                            }
                        }
                    } catch (err: Exception) {
                        Log.e("MainActivity", "Failed to get results for term \"$term\": $err")
                    }
                }
            }.awaitAll()
        }
    }

    private suspend fun doSearch(): List<Pair<String, Int>> {
        return coroutineScope {
            artists.map { aog ->
                async(Dispatchers.IO) {
                    val localResultLength = try {
                        getGalleryIdsForQuery(aog, originState.copy())
                            ?.filterNot { negativeResultSet.contains(it) }
                            ?.size ?: 0
                    } catch (err: Exception) {
                        Log.e("REQUEST", "Failed to get results for term \"$aog\": $err")
                        0
                    }
                    aog to localResultLength
                }
            }.awaitAll()
        }
    }

    private fun getGalleryIdsForQuery(query: String, state: QueryState): List<Int>? {
        val (leftSide, rightSide) = query.replace("_", " ").split(":", limit = 2).let {
            (it.getOrNull(0) ?: "") to (it.getOrNull(1) ?: "")
        }
        return if (rightSide.isNotEmpty()) {
            when {
                leftSide.endsWith("male") -> {
                    state.apply {
                        area = "tag"; tag = query
                    }
                }
                leftSide == "language" -> {
                    state.language = rightSide
                }
                else -> {
                    state.apply {
                        area = leftSide; tag = rightSide
                    }
                }
            }
            getGalleryIdsFromNozomi(state)
        } else {
            emptyList()
        }
    }

    private fun getGalleryIdsFromNozomi(state: QueryState): List<Int>? {
        val pathSegment = if ("all" == state.area) "" else "${state.area}/"
        val commonTag = "${state.tag}-${state.language}"
        val address = "https://${Constants.DOMAIN}/${Constants.COMPRESSED_NOZOMI_PREFIX}/$pathSegment$commonTag${Constants.NOZOMI_EXTENSION}"
        val request = Request.Builder().url(address).build()

        return httpClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                Log.e("REQUEST", response.code.toString() + " " + address)
                return null
            }

            return response.body?.bytes()?.let { bytes ->
                ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN).run {
                    List(remaining() / 4) { int }
                }
            }
        }
    }

    private fun saveJsonOutput() {
        val bookmarks: List<HentoidBookmark> = requestResult.mapIndexed { idx, (tag, cnt) ->
            val name = tag.split(":")[1]
            val encodedQuery = Uri.encode("$tag ${negativeTerms.joinToString(" ")}", "UTF-8")
            HentoidBookmark(
                Constants.SITE_HITOMI,
                "$name $cnt",
                "https://hitomi.la/search.html?$encodedQuery",
                idx + 1
            )
        }
        val gson = GsonBuilder().create()
        val jsonString = gson.toJson(HentoidExport(bookmarks))

        val filename = "output.json"
        val rootPath = Environment.getExternalStorageDirectory().path
        val file = File(rootPath, filename)
        try {
            try {
                DocumentsContract.deleteDocument(contentResolver, openFileUri!!)
            } catch (err: Exception) {}
            FileOutputStream(file).use { outputStream ->
                outputStream.write(jsonString.toByteArray())
            }
            Toast.makeText(this, "JSON 저장 완료!", Toast.LENGTH_SHORT).show()
        } catch (err: Exception) {
            Toast.makeText(this, "저장 실패, $err", Toast.LENGTH_SHORT).show()
        }
    }
}