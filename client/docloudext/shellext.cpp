#include <windows.h>

/* strsafe.h-wrapper for mingw, in order to suppress
 * warnings due to lack of strsafe.lib
 */
#ifdef __MINGW32__
#ifdef __CRT__NO_INLINE
#undef __CRT__NO_INLINE
#define DID_UNDEFINE__CRT__NO_INLINE
#endif
extern "C" {
#endif
#include <strsafe.h>
#ifdef __MINGW32__
}
#ifdef DID_UNDEFINE__CRT__NO_INLINE
#define __CRT__NO_INLINE
#endif
#endif

#define NO_SHLWAPI_STRFCNS
#include <shlwapi.h>
#include "shellext.h"
#include "resource.h"
#include "fileinfo.h"
#include <stdio.h>

extern HINSTANCE g_hInst;
extern long g_cDllRef;
FORMATETC fmte = {CF_HDROP, (DVTARGETDEVICE FAR *)NULL, DVASPECT_CONTENT, -1, TYMED_HGLOBAL };

#define IDCMD_ADD		0
#define IDCMD_REMOVE		1

/* Used for debugging */
#define log(str, ...)

/* Do not check files that do not have a complete path,
 * e.g. c:\a is ok, but not c:
 */
#define MIN_PATH_LEN		4

ShellExt::ShellExt(void) : m_cRef(1), 
	dataObj(NULL),
	moduleFilename(NULL)
{
	wchar_t filename[MAX_PATH];
	InterlockedIncrement(&g_cDllRef);
	HRESULT ret;

	// Load the bitmap for the menu item. 
	// If you want the menu item bitmap to be transparent, the color depth of 
	// the bitmap must not be greater than 8bpp.
	//m_hMenuBmp = LoadImage(g_hInst, MAKEINTRESOURCE(IDB_OK), 
	//   IMAGE_BITMAP, 0, 0, LR_DEFAULTSIZE | LR_LOADTRANSPARENT);

	ret = GetModuleFileName(g_hInst, filename, ARRAYSIZE(filename));

	/* Ignore errors and keep moduleFilename as NULL -
	 * we'll lose our overlayicons, but everything else works
	 */
	if (ret > 0 && ret < MAX_PATH)
	{
		moduleFilename = new wchar_t[ret+1];
		StringCchCopy(moduleFilename, ret+1, filename);
	}
}

ShellExt::~ShellExt(void)
{
	if (m_hMenuBmp)
	{
		DeleteObject(m_hMenuBmp);
		m_hMenuBmp = NULL;
	}

	if (moduleFilename)
		delete moduleFilename;

	InterlockedDecrement(&g_cDllRef);
}



/* IUnknown Interface {{{ */

// Query to the interface the component supported.
STDMETHODIMP ShellExt::QueryInterface(REFIID riid, LPVOID FAR *ppv)
{
	*ppv = NULL;

	if (IsEqualIID(riid, IID_IShellExtInit) || IsEqualIID(riid, IID_IUnknown))
		*ppv = (LPSHELLEXTINIT)this;
	else if (IsEqualIID(riid, IID_IContextMenu))
		*ppv = (LPCONTEXTMENU)this;
	else if (IsEqualIID(riid, IID_IShellIconOverlayIdentifier))
		*ppv = (IShellIconOverlayIdentifier*)this;

	if (*ppv) {
		AddRef();
		return NOERROR;
	}

	return E_NOINTERFACE;
}

// Increase the reference count for an interface on an object.
STDMETHODIMP_(ULONG) ShellExt::AddRef()
{
	return InterlockedIncrement(&m_cRef);
}

// Decrease the reference count for an interface on an object.
STDMETHODIMP_(ULONG) ShellExt::Release()
{
	if (InterlockedDecrement(&m_cRef))
		return m_cRef;

	delete this;
	return 0L;
}

/* }}} END IUnknown Interface */
/* IShellExtInit Interface {{{ */

// Initialize the context menu handler.
STDMETHODIMP
ShellExt::Initialize(LPCITEMIDLIST pidlFolder,
    LPDATAOBJECT pDataObj, HKEY hKeyProgID)
{

	if (dataObj != NULL)
		dataObj->Release();

	if (pDataObj) {
		dataObj = pDataObj;
		pDataObj->AddRef();
	}

	return S_OK;
}

/* }}} END IShellExtInit Interface */
/* IContextMenu Interface {{{ */

/*
 * QueryContextMenu()
 * Add items to contextmenu for matching files
 */
STDMETHODIMP
ShellExt::QueryContextMenu(HMENU hMenu, UINT indexMenu,
    UINT idCmdFirst, UINT idCmdLast, UINT uFlags)
{
	HRESULT hres;
	UINT idCmd;
	const wchar_t *text;
	int ret;

	// If uFlags include CMF_DEFAULTONLY then we should not do anything.
	if (CMF_DEFAULTONLY & uFlags)
	{
		return MAKE_HRESULT(SEVERITY_SUCCESS, 0, USHORT(0));
	}

	hres = dataObj->GetData(&fmte, &medium);

	nFiles = 0;
	if (medium.hGlobal)
		nFiles = DragQueryFile((HDROP)medium.hGlobal, (UINT)-1, 0, 0);

	idCmd = idCmdFirst;

	/* Build list of files, with info */
	int found = 0;
	int blacklisted = 0;

	v_files.resize(nFiles);
	for (int i = 0; i < nFiles; i++) {
		wchar_t filename[300];
		char filename_utf8[300];
		struct file_info file;


		DragQueryFile((HDROP)medium.hGlobal, i, filename, ARRAYSIZE(filename));

		/* FIXME! - check return value? */
		WideCharToMultiByte(CP_UTF8, 0, filename, -1,
		    filename_utf8, sizeof(filename_utf8), NULL, NULL);

		if (strlen(filename_utf8) < MIN_PATH_LEN) {
			v_files[i].filename = NULL;
			continue;
		}

		v_files[i].id = -1;
		v_files[i].filename = strdup(filename_utf8);
		v_files[i].parent_flags = 0;
		v_files[i].blacklisted = 0;

		ret = docloud_get_file_info(&(v_files[i]));
		log("docloud_get_file_info(%d: %s): %d\n", v_files[i].id, v_files[i].filename, ret);
		if (ret == DC_OK) {
			found++;
			if (v_files[i].blacklisted) blacklisted ++;
			break;
		}
	}

	if (found && !blacklisted) {
		if (nFiles > 1) text = L"Remove files from doCloud";
		else text = L"Remove file from doCloud";
		idCmd += IDCMD_REMOVE;
	} else {
		if (nFiles > 1) text = L"Add files to doCloud";
		else text = L"Add file to doCloud";
		idCmd += IDCMD_ADD;
	}

	InsertMenu(hMenu, indexMenu++, MF_STRING|MF_BYPOSITION, idCmd++, text);
	InsertMenu(hMenu, indexMenu++, MF_SEPARATOR|MF_BYPOSITION, 0, NULL);

	return MAKE_HRESULT(SEVERITY_SUCCESS, 0, USHORT(idCmd - idCmdFirst));
	/*
	 * Menuitem with bitmap:
	 *
	 
	   MENUITEMINFO mii = { sizeof(mii) };
	   mii.fMask = MIIM_BITMAP | MIIM_STRING | MIIM_FTYPE | MIIM_ID | MIIM_STATE;
	   mii.wID = idCmdFirst + IDM_DISPLAY;
	   mii.fType = MFT_STRING;

	   if (nFiles == 1)
	   mii.dwTypeData = m_pszMenuText;
	   else
	   mii.dwTypeData = L"&Multiple files!!!";
	   mii.fState = MFS_ENABLED;
	   mii.hbmpItem = static_cast<HBITMAP>(m_hMenuBmp);
	   if (!InsertMenuItem(hMenu, indexMenu, TRUE, &mii))
	   {
	   return HRESULT_FROM_WIN32(GetLastError());
	   }

*/
}


STDMETHODIMP ShellExt::InvokeCommand(LPCMINVOKECOMMANDINFO pici)
{
	BOOL fUnicode = FALSE;
	int ret;

	/* We're only interested in user actions -
	 * and if HIWORD(pici->lpVerb) > 0, we've been called programmatically
	 */
	if (HIWORD(pici->lpVerb))
		return E_INVALIDARG;

	UINT cmd;
	cmd = LOWORD(pici->lpVerb);

	for (int i = 0; i < nFiles; i++) {
		if (v_files[i].filename == NULL)
			continue;
		if (cmd == IDCMD_ADD) {
			if (v_files[i].id) v_files[i].blacklisted = 0;
			ret = docloud_add_file(&v_files[i]);
			log("add file %s: %d\n", v_files[i].filename, ret);
		} else if (cmd == IDCMD_REMOVE) {
			v_files[i].blacklisted = 1;
			ret = docloud_add_file(&v_files[i]);
			log("blacklist file %s: %d\n", v_files[i].filename, ret);
		}
	}
	//	OnVerbDisplayFileName(pici->hwnd);
	return S_OK;

}

STDMETHODIMP ShellExt::GetCommandString(UINT_PTR idCommand, 
    UINT uFlags, UINT *pwReserved, LPSTR pszName, UINT cchMax)
{
	HRESULT hr = S_OK;
	if (uFlags == GCS_HELPTEXTW && cchMax > 35)
		hr = StringCchCopy(reinterpret_cast<PWSTR>(pszName), cchMax, L"Add file to doCloud");

	return S_OK;
}

/* }}} END IContextMenu Interface */
/* IShellIconOverlayIdentifier Interface {{{ */

STDMETHODIMP
ShellExt::GetOverlayInfo(PWSTR pwszIconFile, int cchMax,int *pIndex,DWORD *pdwFlags)
{
	*pdwFlags = 0;
	if (moduleFilename) {
		StringCchCopy(reinterpret_cast<PWSTR>(pwszIconFile), cchMax, moduleFilename);
		*pIndex = 0;
		*pdwFlags = ISIOI_ICONFILE;
	}
	return S_OK;
}

STDMETHODIMP
ShellExt::GetPriority(int *priority)
{
	*priority = 50;
	return S_OK;
}

STDMETHODIMP
ShellExt::IsMemberOf(PCWSTR pwszPath, DWORD dwAttrib)
{
	char filename_utf8[250];
	struct file_info file;
	int ret;

	WideCharToMultiByte(CP_UTF8, 0, pwszPath, -1,
	    filename_utf8, sizeof(filename_utf8), NULL, NULL);

	if (strlen(filename_utf8) < MIN_PATH_LEN)
		return S_FALSE;

	if (!docloud_is_correct_filetype(filename_utf8)) {
		return S_FALSE;
	}

	file.id = -1;
	file.filename = filename_utf8;
	//file.parent_flags = DC_PARENT_IGNORE;

	ret = docloud_get_file_info(&file);
	if (ret == DC_OK && (file.id != -1 || file.parent_flags & DC_PARENT_ADDED)) {
		if (file.blacklisted)
			return S_FALSE;
		return S_OK;
	}
	return S_FALSE;
}

/* }}} END IShellIconOverlayIdentifier Interface */

void ShellExt::OnVerbDisplayFileName(HWND hWnd)
{
	wchar_t szMessage[300];
	int nFiles = 0;

	if (medium.hGlobal)
		nFiles = DragQueryFile((HDROP)medium.hGlobal, (UINT)-1, 0, 0);

	StringCchPrintf(szMessage, ARRAYSIZE(szMessage), 
		    L"Your selected file(s):\r\n\r\n");

	for (int i = 0; i < nFiles; i++) {
		wchar_t filename[300];
		DragQueryFile((HDROP)medium.hGlobal, i, filename, ARRAYSIZE(filename));
		StringCchCat(szMessage, ARRAYSIZE(szMessage), filename);
		StringCchCat(szMessage, ARRAYSIZE(szMessage), L"\r\n");

	}
	MessageBox(hWnd, szMessage, L"doCloud", MB_OK);
}