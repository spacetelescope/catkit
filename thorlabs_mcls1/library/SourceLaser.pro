TEMPLATE = app
CONFIG += console c++11
CONFIG -= app_bundle
CONFIG -= qt

SOURCES += \
    MCLS1_Api.cpp \
    JOST_MCLS1.cpp


HEADERS += uart_library.h \
    MCLS1_Api.h


INCLUDEPATH += $$PWD
DEPENDPATH  += $$PWD
