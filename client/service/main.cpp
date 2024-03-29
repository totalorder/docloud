#include <windows.h>
#include <direct.h>
#include <getopt.h>
#include <stdio.h>
#include "dirwatcher.h"
#include "sqlitewatcher.h"
#include "service.h"
#include "common.h"

DWORD WINAPI  (__stdcall *service_exec_function)(LPVOID) = NULL;
extern int service_is_running;

DWORD WINAPI thread_dirwatch(LPVOID param)
{
	dirWatcher *d;
	d = (dirWatcher *)param;
	d->watch();
}

DWORD WINAPI thread_sqlitewatch(LPVOID param)
{
	sqliteWatcher *sw;
	sw = (sqliteWatcher *)param;
	sw->watch();
}


DWORD WINAPI thread_work(LPVOID param)
{
	dirWatcher *d;
	d = (dirWatcher *)param;
	d->work();
}

DWORD WINAPI main_loop(LPVOID param)
{
	dirWatcher *d = new dirWatcher;
	sqliteWatcher *sqlw = new sqliteWatcher();
	unsigned long threadid;

	sqlw->setDirWatcher(d);

	CreateThread(NULL, 0, thread_sqlitewatch, sqlw, 0, &threadid);
	printf("Created thread for sqlitewatcher: %d\n", threadid);

	/* Read list of directories from DB */
	d->loadDirList();

	CreateThread(NULL, 0, thread_dirwatch, d, 0, &threadid);
	printf("Created thread for dirwatcher %d\n", threadid);

	CreateThread(NULL, 0, thread_work, d, 0, &threadid);
	printf("Created worker thread %d\n", threadid);

	Sleep(100000);
	delete d;

	return 0;
}

void
usage(const char *filename)
{
	printf("docloud service\n"
	    "  Usage: %s [-iu]\n"
	    "     -i install as service\n"
	    "     -u uninstall service\n", filename);

}

int
main(int argc, char *argv[])
{
	const char *service_name = "doCloud";
	char buf[MAX_PATH];
	int install_as_service = 0;
	int run_as_service = 0;
	int uninstall_service_flag = 0;
	int retval;
	char *ptr;

	/* change CWD to the same directory as the .exe-file */
	strncpy(buf, argv[0], sizeof(buf));
	if ((ptr=strrchr(buf,'/')) || (ptr = strrchr(buf, '\\'))) {
		*ptr = '\0';
		if (_chdir(buf) == -1){
			printf("Cannot change working directory to %s! (%s)\n",buf, strerror(errno));
		}
	}

	int ch;
	while (((ch = getopt(argc, argv, "iud:I:S1"))) != -1) {
		switch (ch) {
			case 'i': /* Install as service */
				install_as_service = 1;
			break;
			case 'u': /* Uninstall as service */
				uninstall_service_flag = 1;
			break;
			case 'S': /* Run as service */
				run_as_service = 1;
				service_exec_function = &main_loop;
				break;
			default:
				usage(argv[0]);
			break;
		}
	}

	if (install_as_service) {
		wchar_t filename[MAX_PATH];
		if (!GetModuleFileName(NULL, filename, sizeof(filename))) {
//				debug_windows("Cannot get filename of executable (%s)!\n");
		}

		std::wstring cmd;
		cmd += L"\"";
		cmd += filename;
		cmd += L"\" -S";

		retval = install_service(widen(service_name).c_str(),
			    widen(service_name).c_str(), cmd.c_str(), NULL, NULL);
		if (retval != -1) {
			printf("Service successfully installed under name %s!\n", service_name);
		}
		return 0;
	}else if (run_as_service) {
		printf("Starting service\n");
		retval = service_start(widen(service_name).c_str(), argc, argv);
	}else if (uninstall_service_flag) {
		retval = uninstall_service(widen(service_name).c_str());
		if (retval != -1) {
			printf("Service successfully uninstalled!\n");
		}
		return 0;
	} 

	if (! run_as_service)
		retval = main_loop(NULL);
}
